from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agents.base import PartyDocs, PolicyDocument, ResolvedParty
from ..agents.debug import ensure_run_dir, save_json
from ..agents.fetchers import HttpxFetcher
from ..agents.llm_clients import GeminiLLMClient, OpenAILLMClient
from ..agents.llm_search import GeminiLLMSearchClient, OpenAILLMSearchClient
from ..agents.scorer import ScoringAgent
from ..agents.text_extract import html_to_text
from ..db import models
from ..settings import settings
from . import policy_index, topic_rubrics


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


def _domain_allowed(netloc: str, allowed_domains: list[str]) -> bool:
    host = (netloc or "").split(":")[0].lower()
    allowed = [d.split(":")[0].lower() for d in (allowed_domains or []) if d]
    if not host or not allowed:
        return False
    if host in allowed:
        return True
    return any(host.endswith("." + d) for d in allowed)


def _make_quote(text: str, *, max_len: int = 280) -> str:
    t = " ".join((text or "").split())
    if not t:
        return ""
    return t[:max_len]

def _toggle_trailing_slash(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    return u[:-1] if u.endswith("/") else (u + "/")


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
    scope: str = "official",
    search_provider: str = "auto",
    search_openai_model: str | None = None,
    search_gemini_model: str | None = None,
    score_provider: str = "auto",
    score_openai_model: str | None = None,
    score_gemini_model: str | None = None,
    max_parties: int | None = None,
    max_evidence_per_party: int = 2,
    max_doc_chars: int = 8000,
    index_only: bool = False,
    debug: bool = False,
) -> models.ScoreRun:
    scope_norm = (scope or "official").strip().lower()
    if scope_norm not in {"official", "mixed"}:
        raise ValueError("scope must be 'official' or 'mixed'")
    allow_external = scope_norm == "mixed"

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
    if max_parties is not None:
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

    used_search_provider = None
    search_client = None
    if not index_only:
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

    # トピック作成/更新時に生成して topics.search_subkeywords に保存したものを使う（スコアリング時に再生成しない）
    subkeywords: list[str] = list(getattr(topic, "search_subkeywords", None) or [])
    subkw_text = " ".join(subkeywords)

    docs_by_party: Dict[str, List[PolicyDocument]] = {p.name_ja: [] for p in resolved}
    quote_by_url: dict[str, str] = {}
    official_url_by_party: dict[str, str] = {p.name_ja: p.official_url for p in resolved}

    evidence_list: list = []
    per_party_queries: dict[str, list[str]] = {}
    per_party_query_used: dict[str, str | None] = {}
    grounding_urls_by_party: dict[str, list[str]] = {}
    per_party_attempts_by_party: dict[str, int] = {}
    openai_usage_by_party: dict[str, dict[str, int]] = {}
    evidence_payload_by_party: dict[str, dict | None] = {}
    candidate_urls_by_party: dict[str, list[str]] = {}
    url_checks_by_party: dict[str, list[dict[str, str | int]]] = {}
    index_hits_count_by_party: dict[str, int] = {}
    index_fallback_used_by_party: dict[str, bool] = {}

    if index_only:
        index_queries = [topic_text, *list(subkeywords or [])]
        max_chunks = max(3, int(max_evidence_per_party) * 2)
        per_query = max(1, int(max_evidence_per_party))
        for p in resolved:
            hits = policy_index.search_policy_chunks(
                db,
                party_id=party_by_name[p.name_ja].party_id,
                queries=index_queries,
                per_query=per_query,
                max_total=max_chunks,
            )
            index_hits_count_by_party[p.name_ja] = len(hits)
            per_party_queries[p.name_ja] = list(index_queries)
            per_party_query_used[p.name_ja] = "index"
            per_party_attempts_by_party[p.name_ja] = 1
            for hit in hits:
                chunk = hit.chunk
                meta = chunk.meta if isinstance(chunk.meta, dict) else {}
                url = (meta.get("source_url") or "").strip()
                content = (chunk.content or "").strip()
                if not url or not content:
                    continue
                docs_by_party[p.name_ja].append(PolicyDocument(url=url, content=content[:max_doc_chars]))
                if url not in quote_by_url:
                    quote_by_url[url] = _make_quote(content)
            if docs_by_party[p.name_ja]:
                candidate_urls_by_party[p.name_ja] = [d.url for d in docs_by_party[p.name_ja]]
    else:
        # 根拠URLのハルシネーションを減らすため、政党ごとに検索する
        for p in resolved:
            host = (urlparse(p.official_url).netloc or "").lower()
            base = host.removeprefix("www.") if hasattr(host, "removeprefix") else (host[4:] if host.startswith("www.") else host)
            if used_search_provider == "openai":
                # OpenAI web_search では filters.allowed_domains でドメイン絞り込みできるため、site: は付けない（精度/ヒット率を優先）
                variants = [
                    f"{topic_text} {subkw_text} 政策 公約",
                    f"{topic_text} {subkw_text} 提言 マニフェスト",
                    f"{topic_text} {subkw_text}",
                ]
            else:
                if allow_external:
                    variants = [
                        f"{topic_text} {subkw_text} 政策 公約",
                        f"{topic_text} {subkw_text} 提言 マニフェスト",
                        f"{topic_text} {subkw_text}",
                    ]
                else:
                    # Geminiはドメイン絞り込みが弱いので site: を付けて寄せる
                    variants = [
                        f"site:{base} {topic_text} {subkw_text} 政策 公約",
                        f"site:{base} {topic_text} {subkw_text} 提言 マニフェスト",
                        f"site:{base} {topic_text} {subkw_text}",
                    ]
            variants = [" ".join(v.split()).strip() for v in variants if v and v.strip()]
            per_party_queries[p.name_ja] = variants
            per_party_query_used[p.name_ja] = None
            per_party_attempts_by_party[p.name_ja] = 0
            if used_search_provider == "openai":
                openai_usage_by_party[p.name_ja] = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

            for query in variants:
                per_party_attempts_by_party[p.name_ja] += 1
                topic_with_query = f"{topic_text}\n検索クエリ: {query}"
                res = search_client.find_policy_evidence_bulk(
                    topic=topic_with_query,
                    parties=[p],
                    max_per_party=max_evidence_per_party,
                    allowed_domains=([] if allow_external and used_search_provider == "openai" else None),
                )
                evidence_list.extend(res or [])
                grounding_urls_by_party[p.name_ja] = list(getattr(search_client, "last_grounding_urls", None) or [])
                if used_search_provider == "openai":
                    usage = getattr(search_client, "last_usage", None) or {}
                    if isinstance(usage, dict):
                        for k in ("input_tokens", "output_tokens", "total_tokens"):
                            v = usage.get(k)
                            if isinstance(v, int):
                                openai_usage_by_party[p.name_ja][k] = int(openai_usage_by_party[p.name_ja].get(k, 0)) + int(v)
                evidence_payload_by_party[p.name_ja] = getattr(search_client, "last_evidence_payload", None)
                has_any = False
                for it in res or []:
                    if (it.party_name or "") == p.name_ja and getattr(it, "evidence", None):
                        has_any = True
                        break
                if has_any:
                    per_party_query_used[p.name_ja] = query
                    urls = []
                    for it in res or []:
                        if (it.party_name or "") != p.name_ja:
                            continue
                        for ev in list(getattr(it, "evidence", None) or []):
                            url = (getattr(ev, "evidence_url", None) or "").strip()
                            if url:
                                urls.append(url)
                    if urls:
                        candidate_urls_by_party[p.name_ja] = urls
                    break

    fetcher = HttpxFetcher(timeout=30)
    def _expand_domains(domains: list[str]) -> list[str]:
        out: set[str] = set()
        for d in domains or []:
            dd = (d or "").strip().lower()
            if not dd:
                continue
            out.add(dd)
            if dd.startswith("www."):
                out.add(dd.removeprefix("www."))
            else:
                out.add("www." + dd)
        return list(out)

    allowed_domains_by_party: dict[str, list[str]] = {
        p.name_ja: _expand_domains([urlparse(p.official_url).netloc, *list(p.allowed_domains or [])]) for p in resolved
    }

    def _record_url_check(party_name: str, url: str, status: int | None, reason: str) -> None:
        if not settings.agent_save_runs:
            return
        payload = {"url": url, "reason": reason}
        if status is not None:
            payload["status"] = int(status)
        url_checks_by_party.setdefault(party_name, []).append(payload)

    for item in evidence_list:
        party_name = item.party_name
        if party_name not in docs_by_party:
            party_name = resolved_name_by_canonical.get(_canonicalize_name_ja(party_name), party_name)
        if party_name not in docs_by_party:
            continue

        grounded_urls = grounding_urls_by_party.get(party_name, [])
        grounded_by_domain: dict[str, list[str]] = {}
        for u in grounded_urls:
            try:
                pu = urlparse(u)
            except Exception:
                continue
            if pu.scheme not in {"http", "https"} or not pu.netloc:
                continue
            key = pu.netloc.lower()
            grounded_by_domain.setdefault(key, [])
            if u not in grounded_by_domain[key]:
                grounded_by_domain[key].append(u)

        def _replacement_urls_for_party(party_name_: str) -> list[str]:
            allowed = allowed_domains_by_party.get(party_name_, [])
            out: list[str] = []
            for dom, urls in grounded_by_domain.items():
                if not _domain_allowed(dom, allowed):
                    continue
                out.extend(urls)
            seen: set[str] = set()
            dedup: list[str] = []
            for u2 in out:
                if u2 in seen:
                    continue
                seen.add(u2)
                dedup.append(u2)
            return dedup

        candidates = [ev.evidence_url for ev in item.evidence[:max_evidence_per_party] if ev.evidence_url]
        # LLMが返したURLが404等の場合に備えて、grounding由来のURL候補も併用（公式のみの場合）
        if not allow_external:
            candidates.extend(_replacement_urls_for_party(party_name))

        used: set[str] = set()
        for url in candidates:
            if not url or url in used:
                continue
            used.add(url)
            if _is_homepage_url(url, official_url_by_party.get(party_name, "")):
                _record_url_check(party_name, url, None, "skip_homepage")
                continue

            pu = urlparse(url)
            if (not allow_external) and (not _domain_allowed(pu.netloc, allowed_domains_by_party.get(party_name, []))):
                _record_url_check(party_name, url, None, "skip_domain_not_allowed")
                continue

            quote = ""
            for ev in item.evidence:
                if ev.evidence_url == url and (ev.quote or "").strip():
                    quote = (ev.quote or "").strip()
                    break

            resp = None
            try:
                resp = fetcher.client.get(url, timeout=fetcher.client.timeout)
            except Exception:
                resp = None

            if resp is not None:
                status = int(getattr(resp, "status_code", 0) or 0)
                if status == 404:
                    alt = _toggle_trailing_slash(url)
                    if alt and alt != url:
                        try:
                            resp2 = fetcher.client.get(alt, timeout=fetcher.client.timeout)
                        except Exception:
                            resp2 = None
                        if resp2 is not None:
                            status2 = int(getattr(resp2, "status_code", 0) or 0)
                            if 200 <= status2 < 400:
                                try:
                                    text2 = html_to_text(resp2.text)
                                except Exception:
                                    text2 = ""
                                text2 = (text2 or "").strip()
                                if text2:
                                    _record_url_check(party_name, alt, status2, "accepted_alt_url")
                                    quote_by_url[alt] = quote or _make_quote(text2)
                                    docs_by_party[party_name].append(PolicyDocument(url=alt, content=text2[:max_doc_chars]))
                                    if len(docs_by_party[party_name]) >= max_evidence_per_party:
                                        break
                                    continue
                        _record_url_check(party_name, alt, status2 if resp2 is not None else None, "alt_url_not_usable")
                    _record_url_check(party_name, url, status, "not_found")
                    continue  # 実在しないURLは採用しない
                if 200 <= status < 400:
                    try:
                        text = html_to_text(resp.text)
                    except Exception:
                        text = ""
                    text = (text or "").strip()
                    if text:
                        if allow_external and (not _domain_allowed(pu.netloc, allowed_domains_by_party.get(party_name, []))):
                            if party_name not in text:
                                _record_url_check(party_name, url, status, "skip_external_no_party_name")
                                continue
                        _record_url_check(party_name, url, status, "accepted")
                        quote_by_url[url] = quote or _make_quote(text)
                        docs_by_party[party_name].append(PolicyDocument(url=url, content=text[:max_doc_chars]))
                        if len(docs_by_party[party_name]) >= max_evidence_per_party:
                            break
                        continue
                    _record_url_check(party_name, url, status, "skip_empty_text")
                else:
                    _record_url_check(party_name, url, status, "skip_http_status")
            else:
                _record_url_check(party_name, url, None, "fetch_error")

            # 取得できないURLは根拠として採用しない（URLハルシネーション対策）
            continue

    if not index_only:
        index_queries = [topic_text, *list(subkeywords or [])]
        max_chunks = max(3, int(max_evidence_per_party) * 2)
        max_docs = max(3, int(max_evidence_per_party) * 2)
        per_query = max(1, int(max_evidence_per_party))
        for p in resolved:
            party_name = p.name_ja
            hits = policy_index.search_policy_chunks(
                db,
                party_id=party_by_name[party_name].party_id,
                queries=index_queries,
                per_query=per_query,
                max_total=max_chunks,
            )
            index_hits_count_by_party[party_name] = len(hits)
            if not hits:
                continue
            docs = docs_by_party.get(party_name) or []
            seen_urls: set[str] = {d.url for d in docs if d.url}
            for hit in hits:
                if len(docs_by_party[party_name]) >= max_docs:
                    break
                chunk = hit.chunk
                meta = chunk.meta if isinstance(chunk.meta, dict) else {}
                url = (meta.get("source_url") or "").strip()
                content = (chunk.content or "").strip()
                if not url or not content or url in seen_urls:
                    continue
                docs_by_party[party_name].append(PolicyDocument(url=url, content=content[:max_doc_chars]))
                seen_urls.add(url)
                index_fallback_used_by_party[party_name] = True
                if url not in quote_by_url:
                    quote_by_url[url] = _make_quote(content)

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
    doc_urls_by_party: dict[str, set[str]] = {
        pd.party_name: {d.url for d in pd.docs if d.url} for pd in party_docs
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
            "scope": scope_norm,
            "topic_text": topic_text,
            "retrieval_mode": "index" if index_only else "search",
            "index_only": index_only,
            "include_external": allow_external,
            "max_parties": max_parties,
            "max_evidence_per_party": max_evidence_per_party,
            "created_at": _now_iso(),
            "evidence_search": {
                "mode": "index" if index_only else "search",
                "last_error": (getattr(search_client, "last_error", None) if search_client else None),
                "per_party_queries": per_party_queries,
                "per_party_query_used": per_party_query_used,
                "subkeywords": subkeywords,
                "index_hits_count_by_party": index_hits_count_by_party,
                "index_fallback_used_by_party": index_fallback_used_by_party,
                "grounding_urls_count_by_party": {k: len(v or []) for k, v in grounding_urls_by_party.items()},
                "per_party_attempts_by_party": per_party_attempts_by_party,
                "openai_usage_by_party": (openai_usage_by_party if used_search_provider == "openai" else None),
                "evidence_payload_by_party": evidence_payload_by_party,
            },
            "results_raw": [asdict(r) for r in results],
        },
    )
    db.add(run)
    db.flush()

    evidence_items_by_party: dict[str, list[dict[str, str]]] = {}
    for r in results:
        party_name = r.party_name
        party = party_by_name.get(party_name)
        if not party:
            party_name = resolved_name_by_canonical.get(_canonicalize_name_ja(party_name), party_name)
            party = party_by_name.get(party_name)
        if not party:
            continue

        official_url = official_url_by_party.get(party_name, party.official_home_url or "")
        doc_urls = [d.url for d in (docs_by_party.get(party_name) or []) if getattr(d, "url", None)]
        non_home_doc_urls = [u for u in doc_urls if not _is_homepage_url(u, official_url)]
        # スコアリングLLMが返すevidence_urlはハルシネーションの可能性があるため、
        # 収集した根拠URL（取得/検証済み）に含まれる場合のみ採用する。
        candidate_url = (r.evidence_url or "").strip() if getattr(r, "evidence_url", None) else ""
        if candidate_url and candidate_url in doc_urls_by_party.get(party_name, set()):
            evidence_url = candidate_url
        else:
            evidence_url = first_doc_url_by_party.get(party_name)

        if not evidence_url:
            evidence_url = (non_home_doc_urls[0] if non_home_doc_urls else (doc_urls[0] if doc_urls else None))

        evidence_quote = (quote_by_url.get(evidence_url) if evidence_url else None) or None

        evidence_items: list[dict[str, str]] = []
        if evidence_url:
            evidence_items.append({"url": evidence_url, "quote": evidence_quote or ""})
        for u in non_home_doc_urls:
            if len(evidence_items) >= max(1, int(max_evidence_per_party)):
                break
            if u == evidence_url:
                continue
            evidence_items.append({"url": u, "quote": quote_by_url.get(u, "")})
        evidence_items_by_party[party_name] = list(evidence_items)

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
                evidence_quote=evidence_quote,
                evidence=evidence_items,
            )
        )

    db.commit()
    db.refresh(run)

    if settings.agent_save_runs:
        run_dir = ensure_run_dir(Path(__file__).resolve().parents[2] / "runs" / "scoring")
        save_json(
            True,
            run_dir / f"score_{topic_id}_{scope_norm}_{run.run_id}.json",
            {
                "run_id": str(run.run_id),
                "topic_id": topic_id,
                "scope": scope_norm,
                "topic_text": topic_text,
                "retrieval_mode": "index" if index_only else "search",
                "index_only": index_only,
                "search_provider": used_search_provider,
                "score_provider": used_score_provider,
                "search_model": getattr(search_client, "model", None),
                "score_model": getattr(score_client, "model", None),
                "allow_external": allow_external,
                "max_parties": max_parties,
                "max_evidence_per_party": max_evidence_per_party,
                "subkeywords": subkeywords,
                "per_party_queries": per_party_queries,
                "per_party_query_used": per_party_query_used,
                "per_party_attempts": per_party_attempts_by_party,
                "index_hits_count_by_party": index_hits_count_by_party,
                "index_fallback_used_by_party": index_fallback_used_by_party,
                "grounding_urls_count_by_party": {k: len(v or []) for k, v in grounding_urls_by_party.items()},
                "candidate_urls_by_party": candidate_urls_by_party,
                "allowed_domains_by_party": allowed_domains_by_party,
                "url_checks_by_party": url_checks_by_party,
                "docs_by_party": {
                    k: [{"url": d.url, "content_len": len(d.content or "")} for d in v] for k, v in docs_by_party.items()
                },
                "evidence_items_by_party": evidence_items_by_party,
                "results_raw": [asdict(r) for r in results],
            },
        )
    return run


def list_latest_topic_scores(
    db: Session,
    *,
    topic_id: str,
    scope: str = "official",
    limit: int = 1,
) -> tuple[Optional[models.ScoreRun], list[models.TopicScore]]:
    scope_norm = (scope or "official").strip().lower()
    if scope_norm not in {"official", "mixed"}:
        raise ValueError("scope must be 'official' or 'mixed'")

    q = select(models.ScoreRun).where(models.ScoreRun.topic_id == topic_id)
    if scope_norm == "mixed":
        q = q.where(models.ScoreRun.meta["scope"].astext == "mixed")  # type: ignore[attr-defined]
    else:
        q = q.where((models.ScoreRun.meta["scope"].astext == "official") | (models.ScoreRun.meta["scope"].astext.is_(None)))  # type: ignore[attr-defined]

    run = db.scalar(q.order_by(models.ScoreRun.created_at.desc()).limit(max(1, int(limit))))
    if not run:
        return None, []
    scores = list(db.scalars(select(models.TopicScore).where(models.TopicScore.run_id == run.run_id)))
    return run, scores
