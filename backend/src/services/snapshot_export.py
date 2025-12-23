from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models
from ..schemas import Evidence, ScoreItem, ScoreMeta, Topic, TopicDetailResponse, TopicPositionsResponse
from . import public_data


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _axis_labels(rubric: models.TopicRubric | None) -> tuple[str | None, str | None]:
    axis_left = rubric.axis_a_label if rubric else None
    axis_right = rubric.axis_b_label if rubric else None
    if rubric and isinstance(rubric.steps, list) and rubric.steps:
        try:
            steps_sorted = sorted(
                [st for st in rubric.steps if isinstance(st, dict) and isinstance(st.get("score"), int)],
                key=lambda st: int(st["score"]),
            )
            if steps_sorted:
                axis_left = str(steps_sorted[0].get("label") or axis_left or "")
                axis_right = str(steps_sorted[-1].get("label") or axis_right or "")
        except Exception:
            pass
    return axis_left, axis_right


def _build_evidence_list(
    *,
    score_row: models.TopicScore,
    fallback_url: str | None,
    fetched_at: datetime,
) -> list[Evidence]:
    evidence_items: list[Evidence] = []
    payload = getattr(score_row, "evidence", None)
    if isinstance(payload, list):
        for ev in payload:
            if not isinstance(ev, dict):
                continue
            url = (ev.get("url") or ev.get("evidence_url") or "").strip()
            if not url:
                continue
            quote = str(ev.get("quote") or ev.get("evidence_quote") or "")
            ev_fetched_at = ev.get("fetched_at") or fetched_at
            quote_start = int(ev.get("quote_start") or 0)
            quote_end = int(ev.get("quote_end") or len(quote))
            evidence_items.append(
                Evidence(
                    url=url,
                    fetched_at=ev_fetched_at,
                    quote=quote,
                    quote_start=quote_start,
                    quote_end=quote_end,
                )
            )
    if evidence_items:
        return evidence_items

    quote = score_row.evidence_quote or ""
    url = score_row.evidence_url or (fallback_url or "")
    if url:
        return [
            Evidence(
                url=url,
                fetched_at=fetched_at,
                quote=quote,
                quote_start=0,
                quote_end=len(quote),
            )
        ]
    return []


def build_topic_positions(db: Session, topic_id: str) -> TopicPositionsResponse | None:
    topic_row = public_data.get_topic(db, topic_id)
    if not topic_row:
        return None

    topic = Topic(topic_id=topic_row.topic_id, name=topic_row.name, description=topic_row.description)
    rubric = public_data.get_active_rubric(db, topic_id)
    run = public_data.get_latest_score_run(db, topic_id)

    axis_left, axis_right = _axis_labels(rubric)
    rubric_version = rubric.version if rubric else None

    if not run:
        return TopicPositionsResponse(
            topic=topic,
            mode="claim",
            entity="party",
            rubric_version=rubric_version,
            axis_a_label=axis_left,
            axis_b_label=axis_right,
            scores=[],
        )

    scores = public_data.list_scores_for_run(db, run.run_id)
    score_map = {s.party_id: s for s in scores}

    parties = list(db.scalars(select(models.PartyRegistry).order_by(models.PartyRegistry.name_ja.asc())))
    topic_version = f"rubric:v{rubric.version}" if rubric else "rubric:none"
    calc_version = run.created_at.isoformat() if getattr(run, "created_at", None) else _now_utc().isoformat()
    fetched_at = run.created_at or _now_utc()

    items: list[ScoreItem] = []
    for party in parties:
        s = score_map.get(party.party_id)
        if not s:
            items.append(
                ScoreItem(
                    entity_type="party",
                    entity_id=str(party.party_id),
                    entity_name=party.name_ja,
                    topic_id=topic_id,
                    mode="claim",
                    stance_label="not_mentioned",
                    stance_score=0,
                    confidence=0.0,
                    rationale="スコアがありません（未評価または根拠不足）。",
                    evidence=[],
                    meta=ScoreMeta(topic_version=topic_version, calc_version=calc_version),
                )
            )
            continue

        evidence = _build_evidence_list(score_row=s, fallback_url=(party.official_home_url or None), fetched_at=fetched_at)

        items.append(
            ScoreItem(
                entity_type="party",
                entity_id=str(party.party_id),
                entity_name=party.name_ja,
                topic_id=topic_id,
                mode="claim",
                stance_label=s.stance_label,
                stance_score=int(s.stance_score),
                confidence=float(s.confidence),
                rationale=s.rationale,
                evidence=evidence,
                meta=ScoreMeta(topic_version=topic_version, calc_version=calc_version),
            )
        )

    return TopicPositionsResponse(
        topic=topic,
        mode="claim",
        entity="party",
        rubric_version=rubric_version,
        axis_a_label=axis_left,
        axis_b_label=axis_right,
        scores=items,
    )


def build_topic_detail(db: Session, topic_id: str, party_id: str) -> TopicDetailResponse | None:
    positions = build_topic_positions(db, topic_id)
    if not positions:
        return None
    score = next((s for s in positions.scores if s.entity_id == party_id), None)
    if not score:
        return None
    return TopicDetailResponse(
        topic=positions.topic,
        mode=positions.mode,
        entity_id=party_id,
        rubric_version=positions.rubric_version,
        axis_a_label=positions.axis_a_label,
        axis_b_label=positions.axis_b_label,
        score=score,
    )


def build_snapshot(db: Session) -> dict[str, Any]:
    topics = [Topic(topic_id=t.topic_id, name=t.name, description=t.description) for t in public_data.list_topics(db)]
    positions: dict[str, Any] = {}
    runs: dict[str, Any] = {}
    for t in topics:
        p = build_topic_positions(db, t.topic_id)
        if p:
            positions[t.topic_id] = p.model_dump(mode="json")
        run = public_data.get_latest_score_run(db, t.topic_id)
        if run:
            runs[t.topic_id] = {
                "run_id": str(run.run_id),
                "topic_id": run.topic_id,
                "created_at": (run.created_at.isoformat() if getattr(run, "created_at", None) else None),
                "search_provider": getattr(run, "search_provider", None),
                "search_model": getattr(run, "search_model", None),
                "score_provider": getattr(run, "score_provider", None),
                "score_model": getattr(run, "score_model", None),
                "meta": (getattr(run, "meta", None) or {}),
            }

    return {
        "snapshot_version": 1,
        "generated_at": _now_utc().isoformat(),
        "topics": [t.model_dump(mode="json") for t in topics],
        "positions": positions,
        "runs": runs,
    }
