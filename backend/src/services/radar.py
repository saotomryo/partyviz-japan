from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models
from . import public_data
from .topic_taxonomy import CATEGORIES, categorize_topic


@dataclass(frozen=True)
class RadarTopicPoint:
    topic_id: str
    topic_name: str
    stance_score: int
    stance_label: str
    confidence: float


def is_missing_score(score_row: models.TopicScore) -> bool:
    """Exclude clearly synthetic / missing score rows.

    Note: genuine "not_mentioned" can still be a valid score if evidence/confidence exists.
    """

    try:
        conf = float(score_row.confidence or 0)
    except Exception:
        conf = 0.0

    if str(score_row.stance_label or "") != "not_mentioned":
        return False
    if int(score_row.stance_score or 0) != 0:
        return False
    if conf != 0.0:
        return False

    payload = getattr(score_row, "evidence", None)
    has_evidence_payload = isinstance(payload, list) and len(payload) > 0
    has_legacy_evidence = bool(score_row.evidence_url) or bool(score_row.evidence_quote)
    return (not has_evidence_payload) and (not has_legacy_evidence)


def build_party_radar(
    db: Session,
    *,
    party_id: UUID,
    party_name: str | None = None,
    scope: str = "official",
    include_empty_categories: bool = True,
) -> dict:
    scope_norm = (scope or "official").strip().lower()
    if scope_norm not in {"official", "mixed"}:
        scope_norm = "official"

    topics = public_data.list_topics(db)
    topic_by_id = {t.topic_id: t for t in topics}

    run_by_topic_id: dict[str, models.ScoreRun] = {}
    run_ids: list[UUID] = []
    for t in topics:
        run = public_data.get_latest_score_run(db, t.topic_id, scope=scope_norm)
        if not run:
            continue
        run_by_topic_id[t.topic_id] = run
        run_ids.append(run.run_id)

    score_rows: list[models.TopicScore] = []
    if run_ids:
        score_rows = list(
            db.scalars(
                select(models.TopicScore).where(
                    models.TopicScore.party_id == party_id,
                    models.TopicScore.run_id.in_(run_ids),
                )
            )
        )
    score_by_topic_id = {row.topic_id: row for row in score_rows}

    points_by_category: dict[str, list[RadarTopicPoint]] = defaultdict(list)
    included_topics = 0

    for topic_id, run in run_by_topic_id.items():
        score_row = score_by_topic_id.get(topic_id)
        if not score_row:
            continue
        if is_missing_score(score_row):
            continue

        topic = topic_by_id.get(topic_id)
        topic_name = topic.name if topic else topic_id
        category = categorize_topic(topic_id=topic_id, topic_name=topic_name)
        points_by_category[category.key].append(
            RadarTopicPoint(
                topic_id=topic_id,
                topic_name=topic_name,
                stance_score=int(score_row.stance_score),
                stance_label=str(score_row.stance_label or ""),
                confidence=float(score_row.confidence or 0),
            )
        )
        included_topics += 1

    categories_out: list[dict] = []
    for cat in CATEGORIES:
        pts = points_by_category.get(cat.key, [])
        if (not include_empty_categories) and (not pts):
            continue
        scores = sorted(p.stance_score for p in pts)
        categories_out.append(
            {
                "key": cat.key,
                "label": cat.label,
                "count": len(scores),
                "median": float(median(scores)) if scores else None,
                "min": int(scores[0]) if scores else None,
                "max": int(scores[-1]) if scores else None,
                "topics": [
                    {
                        "topic_id": p.topic_id,
                        "topic_name": p.topic_name,
                        "stance_score": p.stance_score,
                        "stance_label": p.stance_label,
                        "confidence": p.confidence,
                    }
                    for p in sorted(pts, key=lambda x: x.topic_id)
                ],
            }
        )

    return {
        "entity_type": "party",
        "entity_id": str(party_id),
        "entity_name": party_name,
        "scope": scope_norm,
        "topic_total": len(topics),
        "topic_included": included_topics,
        "categories": categories_out,
    }


def build_all_party_radars(
    db: Session,
    *,
    scope: str = "official",
    include_topics: bool = False,
    include_empty_categories: bool = True,
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

    party_category_scores: dict[UUID, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    party_category_topics: dict[UUID, dict[str, list[RadarTopicPoint]]] = defaultdict(lambda: defaultdict(list))
    included_topic_ids: dict[UUID, set[str]] = defaultdict(set)

    if run_ids and party_by_id:
        rows = db.scalars(select(models.TopicScore).where(models.TopicScore.run_id.in_(run_ids)))
        for row in rows:
            party = party_by_id.get(row.party_id)
            if not party:
                continue
            topic_id = run_id_to_topic_id.get(row.run_id) or row.topic_id
            topic = topic_by_id.get(topic_id)
            topic_name = topic.name if topic else topic_id

            if is_missing_score(row):
                continue

            category = categorize_topic(topic_id=topic_id, topic_name=topic_name)
            score_val = int(row.stance_score)
            party_category_scores[party.party_id][category.key].append(score_val)
            included_topic_ids[party.party_id].add(topic_id)
            if include_topics:
                party_category_topics[party.party_id][category.key].append(
                    RadarTopicPoint(
                        topic_id=topic_id,
                        topic_name=topic_name,
                        stance_score=score_val,
                        stance_label=str(row.stance_label or ""),
                        confidence=float(row.confidence or 0),
                    )
                )

    out: list[dict] = []
    for party in parties:
        categories_out: list[dict] = []
        for cat in CATEGORIES:
            scores = sorted(party_category_scores.get(party.party_id, {}).get(cat.key, []))
            if (not include_empty_categories) and (not scores):
                continue
            categories_out.append(
                {
                    "key": cat.key,
                    "label": cat.label,
                    "count": len(scores),
                    "median": float(median(scores)) if scores else None,
                    "min": int(scores[0]) if scores else None,
                    "max": int(scores[-1]) if scores else None,
                    "topics": [
                        {
                            "topic_id": p.topic_id,
                            "topic_name": p.topic_name,
                            "stance_score": p.stance_score,
                            "stance_label": p.stance_label,
                            "confidence": p.confidence,
                        }
                        for p in sorted(party_category_topics.get(party.party_id, {}).get(cat.key, []), key=lambda x: x.topic_id)
                    ]
                    if include_topics
                    else [],
                }
            )

        out.append(
            {
                "entity_type": "party",
                "entity_id": str(party.party_id),
                "entity_name": party.name_ja,
                "scope": scope_norm,
                "topic_total": len(topics),
                "topic_included": len(included_topic_ids.get(party.party_id, set())),
                "categories": categories_out,
            }
        )

    return out
