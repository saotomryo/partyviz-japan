from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from sqlalchemy import select

from ..db import get_db
from ..db import models
from ..schemas import Evidence, ScoreItem, ScoreMeta, Topic, TopicDetailResponse, TopicPositionsResponse, TopicsResponse
from ..services import public_data


router = APIRouter()


@router.get("/topics", response_model=TopicsResponse)
def list_topics(db: Session = Depends(get_db)) -> TopicsResponse:
    topics = [
        Topic(topic_id=t.topic_id, name=t.name, description=t.description)
        for t in public_data.list_topics(db)
    ]
    return TopicsResponse(topics=topics)


@router.get("/topics/{topic_id}/positions", response_model=TopicPositionsResponse)
def get_topic_positions(
    topic_id: str,
    mode: str = Query("claim", pattern="^(claim|action|combined)$"),
    entity: str = Query("party", pattern="^(party|party\\+politician)$"),
    db: Session = Depends(get_db),
) -> TopicPositionsResponse:
    if mode != "claim":
        raise HTTPException(status_code=400, detail="only mode=claim is supported for now")
    if entity != "party":
        raise HTTPException(status_code=400, detail="only entity=party is supported for now")

    topic_row = public_data.get_topic(db, topic_id)
    if not topic_row:
        raise HTTPException(status_code=404, detail="topic not found")
    topic = Topic(topic_id=topic_row.topic_id, name=topic_row.name, description=topic_row.description)

    run = public_data.get_latest_score_run(db, topic_id)
    if not run:
        return TopicPositionsResponse(topic=topic, mode=mode, entity=entity, scores=[])
    scores = public_data.list_scores_for_run(db, run.run_id)

    rubric = public_data.get_active_rubric(db, topic_id)
    topic_version = f"rubric:v{rubric.version}" if rubric else "rubric:none"
    calc_version = (
        run.created_at.isoformat()
        if getattr(run, "created_at", None)
        else datetime.now(timezone.utc).isoformat()
    )

    party_map = {p.party_id: p for p in db.scalars(select(models.PartyRegistry))}
    score_by_party_id = {s.party_id: s for s in scores}

    items: list[ScoreItem] = []
    for party_id, party in party_map.items():
        s = score_by_party_id.get(party_id)
        if not s:
            items.append(
                ScoreItem(
                    entity_type="party",
                    entity_id=str(party_id),
                    entity_name=party.name_ja,
                    topic_id=topic_id,
                    mode="claim",
                    stance_label="not_mentioned",
                    stance_score=0,
                    confidence=0.0,
                    rationale="スコア未作成（管理UIでスコアリング実行）",
                    evidence=[
                        Evidence(
                            url=party.official_home_url or "",
                            fetched_at=(run.created_at or datetime.now(timezone.utc)),
                            quote="",
                            quote_start=0,
                            quote_end=0,
                        )
                    ]
                    if party.official_home_url
                    else [],
                    meta=ScoreMeta(topic_version=topic_version, calc_version=calc_version),
                )
            )
            continue

        quote = s.evidence_quote or ""
        items.append(
            ScoreItem(
                entity_type="party",
                entity_id=str(s.party_id),
                entity_name=party.name_ja,
                topic_id=topic_id,
                mode="claim",
                stance_label=s.stance_label,
                stance_score=int(s.stance_score),
                confidence=float(s.confidence),
                rationale=s.rationale,
                evidence=[
                    Evidence(
                        url=s.evidence_url or (party.official_home_url or ""),
                        fetched_at=(run.created_at or datetime.now(timezone.utc)),
                        quote=quote,
                        quote_start=0,
                        quote_end=len(quote),
                    )
                ]
                if (s.evidence_url or party.official_home_url)
                else [],
                meta=ScoreMeta(topic_version=topic_version, calc_version=calc_version),
            )
        )

    axis_left = rubric.axis_a_label if rubric else None
    axis_right = rubric.axis_b_label if rubric else None
    if rubric and isinstance(rubric.steps, list) and rubric.steps:
        try:
            # steps の score の最小/最大を左右ラベルとして採用（スコアの向きと一致させる）
            steps_sorted = sorted(
                [st for st in rubric.steps if isinstance(st, dict) and isinstance(st.get("score"), int)],
                key=lambda st: int(st["score"]),
            )
            if steps_sorted:
                axis_left = str(steps_sorted[0].get("label") or axis_left or "")
                axis_right = str(steps_sorted[-1].get("label") or axis_right or "")
        except Exception:
            pass

    return TopicPositionsResponse(
        topic=topic,
        mode=mode,
        entity=entity,
        rubric_version=(rubric.version if rubric else None),
        axis_a_label=axis_left,
        axis_b_label=axis_right,
        scores=items,
    )


@router.get("/entities/{entity_id}/topics/{topic_id}/detail", response_model=TopicDetailResponse)
def get_topic_detail(
    entity_id: str,
    topic_id: str,
    mode: str = Query("claim", pattern="^(claim|action|combined)$"),
    db: Session = Depends(get_db),
) -> TopicDetailResponse:
    if mode != "claim":
        raise HTTPException(status_code=400, detail="only mode=claim is supported for now")

    topic_row = public_data.get_topic(db, topic_id)
    if not topic_row:
        raise HTTPException(status_code=404, detail="topic not found")
    topic = Topic(topic_id=topic_row.topic_id, name=topic_row.name, description=topic_row.description)

    run = public_data.get_latest_score_run(db, topic_id)
    if not run:
        raise HTTPException(status_code=404, detail="score not found")
    scores = public_data.list_scores_for_run(db, run.run_id)

    try:
        from uuid import UUID

        entity_uuid = UUID(entity_id)
    except Exception:
        raise HTTPException(status_code=400, detail="entity_id must be party_id (uuid)")

    score_row = next((s for s in scores if s.party_id == entity_uuid), None)
    if not score_row:
        raise HTTPException(status_code=404, detail="score not found")

    party = db.get(models.PartyRegistry, entity_uuid)
    rubric = public_data.get_active_rubric(db, topic_id)
    topic_version = f"rubric:v{rubric.version}" if rubric else "rubric:none"
    calc_version = (
        run.created_at.isoformat()
        if getattr(run, "created_at", None)
        else datetime.now(timezone.utc).isoformat()
    )
    quote = score_row.evidence_quote or ""

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

    score = ScoreItem(
        entity_type="party",
        entity_id=str(score_row.party_id),
        entity_name=(party.name_ja if party else None),
        topic_id=topic_id,
        mode="claim",
        stance_label=score_row.stance_label,
        stance_score=int(score_row.stance_score),
        confidence=float(score_row.confidence),
        rationale=score_row.rationale,
        evidence=[
            Evidence(
                url=score_row.evidence_url or (party.official_home_url if party else ""),
                fetched_at=(run.created_at or datetime.now(timezone.utc)),
                quote=quote,
                quote_start=0,
                quote_end=len(quote),
            )
        ]
        if (score_row.evidence_url or (party and party.official_home_url))
        else [],
        meta=ScoreMeta(topic_version=topic_version, calc_version=calc_version),
    )
    return TopicDetailResponse(
        topic=topic,
        mode=mode,
        entity_id=entity_id,
        rubric_version=(rubric.version if rubric else None),
        axis_a_label=axis_left,
        axis_b_label=axis_right,
        score=score,
    )
