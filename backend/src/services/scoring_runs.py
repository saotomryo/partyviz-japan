from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.base import PartyDocs, PolicyDocument, ResolvedParty
from ..agents.fetchers import HttpxFetcher
from ..agents.llm_clients import GeminiLLMClient, OpenAILLMClient
from ..agents.llm_search import GeminiLLMSearchClient, OpenAILLMSearchClient
from ..agents.scorer import ScoringAgent
from ..agents.text_extract import html_to_text
from ..db import models
from ..settings import settings
from . import topic_rubrics


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonicalize_name_ja(name_ja: str) -> str:
    return "".join((name_ja or "").split()).lower()


def _normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    # remove trailing slash for comparisons
    return u[:-1] if u.endswith("/") else u


def _is_homepage_url(url: str, official_url: str) -> bool:
    a = _normalize_url(url)
    b = _normalize_url(official_url)
    if not a or not b:
        return False
    if a == b:
        return True
    pa = urlparse(a)
    pb = urlparse(b)
    if pa.scheme and pb.scheme and pa.netloc == pb.netloc:
        return pa.path in {"", "/"} and pa.query == "" and pa.fragment == ""
    return False


def _pick_search_client(*, provider: str, openai_model: str | None, gemini_model: str | None, debug: bool):
    p = (provider or "auto").lower()
    if p in {"auto", "gemini"} and settings.gemini_api_key:
        return "gemini", GeminiLLMSearchClient(
            api_key=settings.gemini_api_key,
            model=gemini_model or settings.gemini_search_model,
            debug=debug,
        )
    if p in {"auto", "openai"} and settings.openai_api_key:
        return "openai", OpenAILLMSearchClient(
            api_key=settings.openai_api_key,
            model=openai_model or settings.openai_search_model,
            debug=debug,
        )
    raise ValueError("No available LLM provider for evidence search")


def _pick_score_client(*, provider: str, openai_model: str | None, gemini_model: str | None):
    p = (provider or "auto").lower()
    if p in {"auto", "openai"} and settings.openai_api_key:
        return "openai", OpenAILLMClient(api_key=settings.openai_api_key, model=openai_model or settings.openai_score_model)
    if p in {"auto", "gemini"} and settings.gemini_api_key:
        return "gemini", GeminiLLMClient(api_key=settings.gemini_api_key, model=gemini_model or settings.gemini_score_model)
    raise ValueError("No available LLM provider for scoring")


def run_topic_scoring(
    db: Session,
    *,
    topic_id: str,
    topic_text: str,
    search_provider: str = "auto",
    search_openai_model: str | None = None,
    search_gemini_model: str | None = None,
    score_provider: str = "auto",
    score_openai_model: str | None = None,
    score_gemini_model: str | None = None,
    max_parties: int = 10,
    max_evidence_per_party: int = 2,
    max_doc_chars: int = 8000,
    debug: bool = False,
) -> models.ScoreRun:
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise ValueError("topic not found")

    rubric = topic_rubrics.get_active_rubric(db, topic_id) if hasattr(topic_rubrics, "get_active_rubric") else None
    if rubric is None:
        # topic_rubrics モジュール側に関数が無い場合はDBから直接取る
        rubric = db.scalar(
            select(models.TopicRubric)
            .where(models.TopicRubric.topic_id == topic_id, models.TopicRubric.status == "active")
            .order_by(models.TopicRubric.version.desc())
            .limit(1)
        ) or db.scalar(
            select(models.TopicRubric)
            .where(models.TopicRubric.topic_id == topic_id)
            .order_by(models.TopicRubric.version.desc())
            .limit(1)
        )

    parties: list[models.PartyRegistry] = list(
        db.scalars(
            select(models.PartyRegistry)
            .where(models.PartyRegistry.status != "rejected")
            .order_by(models.PartyRegistry.created_at.desc())
        )
    )
    parties = parties[: max(1, int(max_parties))]

    resolved: list[ResolvedParty] = []
    party_by_name: dict[str, models.PartyRegistry] = {}
    resolved_name_by_canonical: dict[str, str] = {}
    for p in parties:
        if not p.official_home_url:
            continue
        resolved.append(
            ResolvedParty(
                name_ja=p.name_ja,
                official_url=p.official_home_url,
                allowed_domains=list(p.allowed_domains or []),
            )
        )
        party_by_name[p.name_ja] = p
        resolved_name_by_canonical[_canonicalize_name_ja(p.name_ja)] = p.name_ja

    used_search_provider, search_client = _pick_search_client(
        provider=search_provider,
        openai_model=search_openai_model,
        gemini_model=search_gemini_model,
        debug=debug,
    )

    used_score_provider, score_client = _pick_score_client(
        provider=score_provider,
        openai_model=score_openai_model,
        gemini_model=score_gemini_model,
    )

    evidence_list = search_client.find_policy_evidence_bulk(
        topic=topic_text,
        parties=resolved,
        max_per_party=max_evidence_per_party,
    )

    fetcher = HttpxFetcher(timeout=30)
    docs_by_party: Dict[str, List[PolicyDocument]] = {p.name_ja: [] for p in resolved}
    quote_by_url: dict[str, str] = {}
    official_url_by_party: dict[str, str] = {p.name_ja: p.official_url for p in resolved}
    for item in evidence_list:
        party_name = item.party_name
        if party_name not in docs_by_party:
            party_name = resolved_name_by_canonical.get(_canonicalize_name_ja(party_name), party_name)
        if party_name not in docs_by_party:
            continue
        for ev in item.evidence[:max_evidence_per_party]:
            url = ev.evidence_url
            if not url:
                continue
            if _is_homepage_url(url, official_url_by_party.get(party_name, "")):
                # 公式トップは原則スキップ（他が取れない場合は後でフォールバック）
                continue
            quote_by_url[url] = ev.quote or ""
            try:
                html = fetcher.fetch(url)
                text = html_to_text(html)
            except Exception:
                text = ""
            text = (text or "").strip()
            if text:
                docs_by_party[party_name].append(PolicyDocument(url=url, content=text[:max_doc_chars]))
                continue
            # フェッチ不可でも、groundingで得た quote があれば最低限の根拠として投入
            quote = (ev.quote or "").strip()
            if quote:
                docs_by_party[party_name].append(PolicyDocument(url=url, content=quote[:max_doc_chars]))

    # フォールバック: 根拠URLが取れない党でも公式トップだけは投入してスコアリング対象にする
    for p in resolved:
        if docs_by_party.get(p.name_ja):
            continue
        try:
            html = fetcher.fetch(p.official_url)
            text = html_to_text(html)
        except Exception:
            continue
        text = (text or "").strip()
        if not text:
            continue
        docs_by_party[p.name_ja] = [PolicyDocument(url=p.official_url, content=text[:max_doc_chars])]

    party_docs: list[PartyDocs] = [
        PartyDocs(party_name=name, docs=docs)
        for name, docs in docs_by_party.items()
        if docs
    ]
    first_doc_url_by_party: dict[str, str] = {
        pd.party_name: pd.docs[0].url for pd in party_docs if pd.docs and pd.docs[0].url
    }

    agent = ScoringAgent(llm_client=score_client)
    topic_payload = {"topic_name": topic_text}
    if rubric is not None:
        topic_payload["rubric"] = {
            "topic_id": topic_id,
            "rubric_version": getattr(rubric, "version", None),
            "axis_a_label": getattr(rubric, "axis_a_label", None),
            "axis_b_label": getattr(rubric, "axis_b_label", None),
            "steps": getattr(rubric, "steps", None),
        }
    results = agent.score(topic=topic_payload, party_docs=party_docs)  # type: ignore[arg-type]

    run = models.ScoreRun(
        topic_id=topic_id,
        search_provider=used_search_provider,
        search_model=getattr(search_client, "model", None),
        score_provider=used_score_provider,
        score_model=getattr(score_client, "model", None),
        meta={
            "topic_text": topic_text,
            "max_parties": max_parties,
            "max_evidence_per_party": max_evidence_per_party,
            "created_at": _now_iso(),
            "evidence_search": {
                "last_error": getattr(search_client, "last_error", None),
                "last_discovery_query": getattr(search_client, "last_discovery_query", None),
                "last_evidence_payload": getattr(search_client, "last_evidence_payload", None),
            },
            "results_raw": [asdict(r) for r in results],
        },
    )
    db.add(run)
    db.flush()

    for r in results:
        party_name = r.party_name
        party = party_by_name.get(party_name)
        if not party:
            party_name = resolved_name_by_canonical.get(_canonicalize_name_ja(party_name), party_name)
            party = party_by_name.get(party_name)
        if not party:
            continue
        evidence_url = r.evidence_url or first_doc_url_by_party.get(party_name)
        db.add(
            models.TopicScore(
                run_id=run.run_id,
                topic_id=topic_id,
                party_id=party.party_id,
                stance_label=r.stance_label or "unknown",
                stance_score=int(r.stance_score),
                confidence=float(r.confidence),
                rationale=r.rationale or "",
                evidence_url=evidence_url,
                evidence_quote=(quote_by_url.get(evidence_url) if evidence_url else None),
                evidence=(
                    [{"url": evidence_url, "quote": quote_by_url.get(evidence_url, "")}]
                    if evidence_url
                    else []
                ),
            )
        )

    db.commit()
    db.refresh(run)
    return run


def list_latest_topic_scores(db: Session, *, topic_id: str, limit: int = 1) -> tuple[Optional[models.ScoreRun], list[models.TopicScore]]:
    run = db.scalar(
        select(models.ScoreRun)
        .where(models.ScoreRun.topic_id == topic_id)
        .order_by(models.ScoreRun.created_at.desc())
        .limit(max(1, int(limit)))
    )
    if not run:
        return None, []
    scores = list(db.scalars(select(models.TopicScore).where(models.TopicScore.run_id == run.run_id)))
    return run, scores
