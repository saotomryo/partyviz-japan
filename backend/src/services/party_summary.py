from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pstdev
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models
from . import public_data
from .radar import is_missing_score


@dataclass(frozen=True)
class TopicStat:
    mean: float
    std: float


def _clean_quote(text: str) -> str:
    t = (text or "").strip().replace("\n", " ").replace("\r", " ")
    return " ".join(t.split())


def _pick_quote(score_row: models.TopicScore) -> str:
    payload = getattr(score_row, "evidence", None)
    if isinstance(payload, list):
        for ev in payload:
            if not isinstance(ev, dict):
                continue
            q = str(ev.get("quote") or ev.get("evidence_quote") or "")
            if q.strip():
                return _clean_quote(q)
    q = score_row.evidence_quote or ""
    if q.strip():
        return _clean_quote(q)
    return ""


def _build_summary_text(
    *,
    pos_topics: list[str],
    neg_topics: list[str],
    near_party: str | None,
    far_party: str | None,
    quote: str | None,
    topic_count: int,
    fiscal_note: str | None,
) -> str:
    pos_part = "・".join(pos_topics[:2])
    neg_part = "・".join(neg_topics[:1])
    phrases = []
    if pos_part:
        phrases.append(f"{pos_part}に積極的")
    if neg_part:
        phrases.append(f"{neg_part}は慎重")
    if phrases:
        lead = f"平均より{('、'.join(phrases))}。"
    else:
        lead = "平均との差が小さい。"

    comp = ""
    if near_party and far_party:
        comp = f"{near_party}に近く、{far_party}とは差が大きい。"
    elif near_party:
        comp = f"{near_party}に近い傾向。"

    extra = f"対象{topic_count}件の相対評価。" if topic_count else ""
    note = f"{fiscal_note}" if fiscal_note else ""

    q = f"根拠:「{quote}」" if quote else ""
    text = f"{lead}{comp}{extra}{note}{q}"

    return text


def _topic_stats(scores: Iterable[int]) -> TopicStat | None:
    vals = list(scores)
    if not vals:
        return None
    if len(vals) == 1:
        return TopicStat(mean=float(vals[0]), std=0.0)
    return TopicStat(mean=mean(vals), std=pstdev(vals))


def build_party_summaries(
    db: Session,
    *,
    scope: str = "official",
) -> list[dict]:
    scope_norm = (scope or "official").strip().lower()
    if scope_norm not in {"official", "mixed"}:
        scope_norm = "official"

    parties = list(
        db.scalars(
            select(models.PartyRegistry)
            .where(models.PartyRegistry.status != "rejected")
            .order_by(models.PartyRegistry.name_ja.asc())
        )
    )
    party_by_id = {p.party_id: p for p in parties}

    topics = public_data.list_topics(db)
    topic_by_id = {t.topic_id: t for t in topics}

    run_id_to_topic_id: dict[UUID, str] = {}
    run_ids: list[UUID] = []
    for t in topics:
        run = public_data.get_latest_score_run(db, t.topic_id, scope=scope_norm)
        if not run:
            continue
        run_ids.append(run.run_id)
        run_id_to_topic_id[run.run_id] = t.topic_id

    topic_scores: dict[str, list[int]] = {}
    party_scores: dict[UUID, dict[str, int]] = {p.party_id: {} for p in parties}
    party_quotes: dict[UUID, dict[str, str]] = {p.party_id: {} for p in parties}

    if run_ids:
        rows = db.scalars(select(models.TopicScore).where(models.TopicScore.run_id.in_(run_ids)))
        for row in rows:
            party = party_by_id.get(row.party_id)
            if not party:
                continue
            if is_missing_score(row):
                continue
            topic_id = run_id_to_topic_id.get(row.run_id) or row.topic_id
            score_val = int(row.stance_score)
            party_scores[party.party_id][topic_id] = score_val
            topic_scores.setdefault(topic_id, []).append(score_val)
            quote = _pick_quote(row)
            if quote:
                party_quotes[party.party_id][topic_id] = quote

    topic_stats = {tid: _topic_stats(vals) for tid, vals in topic_scores.items()}

    party_z: dict[UUID, dict[str, float]] = {}
    for party in parties:
        z_map: dict[str, float] = {}
        for topic_id, score_val in party_scores.get(party.party_id, {}).items():
            stat = topic_stats.get(topic_id)
            if not stat:
                continue
            if stat.std == 0:
                z = 0.0
            else:
                z = (score_val - stat.mean) / stat.std
            z_map[topic_id] = z
        party_z[party.party_id] = z_map

    def distance(a: dict[str, float], b: dict[str, float]) -> float | None:
        keys = set(a.keys()) & set(b.keys())
        if len(keys) < 2:
            return None
        vals = [(a[k] - b[k]) ** 2 for k in keys]
        return sum(vals) / len(vals)

    summaries: list[dict] = []
    for party in parties:
        z_map = party_z.get(party.party_id, {})
        z_items = sorted(z_map.items(), key=lambda x: x[1], reverse=True)
        pos_ids = [tid for tid, _ in z_items[:3]]
        neg_ids = [tid for tid, _ in sorted(z_map.items(), key=lambda x: x[1])[:2]]

        pos_topics = [topic_by_id[tid].name for tid in pos_ids if tid in topic_by_id]
        neg_topics = [topic_by_id[tid].name for tid in neg_ids if tid in topic_by_id]

        # nearest/farthest
        near_party = None
        far_party = None
        dists: list[tuple[float, UUID]] = []
        for other in parties:
            if other.party_id == party.party_id:
                continue
            d = distance(z_map, party_z.get(other.party_id, {}))
            if d is None:
                continue
            dists.append((d, other.party_id))
        if dists:
            dists_sorted = sorted(dists, key=lambda x: x[0])
            near_party = party_by_id[dists_sorted[0][1]].name_ja
            far_party = party_by_id[dists_sorted[-1][1]].name_ja

        quote = ""
        for tid in pos_ids + neg_ids:
            q = party_quotes.get(party.party_id, {}).get(tid)
            if q:
                quote = q
                break

        summary_text = _build_summary_text(
            pos_topics=pos_topics,
            neg_topics=neg_topics,
            near_party=near_party,
            far_party=far_party,
            quote=quote,
            topic_count=len(party_scores.get(party.party_id, {})),
            fiscal_note=None,
        )

        summaries.append(
            {
                "entity_id": str(party.party_id),
                "entity_name": party.name_ja,
                "scope": scope_norm,
                "summary_text": summary_text,
                "positive_topics": pos_topics,
                "negative_topics": neg_topics,
                "near_party": near_party,
                "far_party": far_party,
                "evidence_quote": quote or None,
            }
        )

    return summaries
