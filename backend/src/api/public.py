from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from sqlalchemy import select

from ..db import get_db
from ..db import models
from ..schemas import (
    Evidence,
    PartyRadarResponse,
    ScoreItem,
    ScoreMeta,
    Topic,
    TopicDetailResponse,
    TopicPositionsResponse,
    TopicRubricResponse,
    TopicsResponse,
)
from ..services import public_data
from ..services import radar as radar_service


router = APIRouter()

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
    scope: str = Query("official", pattern="^(official|mixed)$"),
    fallback: int = Query(1, ge=0, le=1, description="mixedが無い場合にofficialへフォールバックする(1)か"),
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

    scope_norm = (scope or "official").strip().lower()
    run = public_data.get_latest_score_run(db, topic_id, scope=scope_norm)
    if (not run) and scope_norm == "mixed" and int(fallback) == 1:
        run = public_data.get_latest_score_run(db, topic_id, scope="official")
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

    party_map = {
        p.party_id: p
        for p in db.scalars(select(models.PartyRegistry).where(models.PartyRegistry.status != "rejected"))
    }
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

        fetched_at = run.created_at or datetime.now(timezone.utc)
        evidence_list = _build_evidence_list(score_row=s, fallback_url=party.official_home_url, fetched_at=fetched_at)
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
                evidence=evidence_list,
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
        run_id=run.run_id,
        run_created_at=run.created_at,
        run_scope=(run.meta or {}).get("scope") if isinstance(run.meta, dict) else None,
        run_meta=(run.meta or None),
        scores=items,
    )


@router.get("/topics/{topic_id}/rubric", response_model=TopicRubricResponse)
def get_topic_rubric(topic_id: str, db: Session = Depends(get_db)) -> TopicRubricResponse:
    rubric = public_data.get_active_rubric(db, topic_id)
    if not rubric:
        raise HTTPException(status_code=404, detail="rubric not found")
    return TopicRubricResponse.model_validate(rubric)


@router.get("/entities/{entity_id}/topics/{topic_id}/detail", response_model=TopicDetailResponse)
def get_topic_detail(
    entity_id: str,
    topic_id: str,
    mode: str = Query("claim", pattern="^(claim|action|combined)$"),
    scope: str = Query("official", pattern="^(official|mixed)$"),
    fallback: int = Query(1, ge=0, le=1, description="mixedが無い場合にofficialへフォールバックする(1)か"),
    db: Session = Depends(get_db),
) -> TopicDetailResponse:
    if mode != "claim":
        raise HTTPException(status_code=400, detail="only mode=claim is supported for now")

    topic_row = public_data.get_topic(db, topic_id)
    if not topic_row:
        raise HTTPException(status_code=404, detail="topic not found")
    topic = Topic(topic_id=topic_row.topic_id, name=topic_row.name, description=topic_row.description)

    scope_norm = (scope or "official").strip().lower()
    run = public_data.get_latest_score_run(db, topic_id, scope=scope_norm)
    if (not run) and scope_norm == "mixed" and int(fallback) == 1:
        run = public_data.get_latest_score_run(db, topic_id, scope="official")
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
    fetched_at = run.created_at or datetime.now(timezone.utc)
    evidence_list = _build_evidence_list(
        score_row=score_row,
        fallback_url=(party.official_home_url if party else None),
        fetched_at=fetched_at,
    )

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
        evidence=evidence_list,
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


@router.get("/entities/{entity_id}/radar", response_model=PartyRadarResponse)
def get_party_radar(
    entity_id: str,
    scope: str = Query("official", pattern="^(official|mixed)$"),
    db: Session = Depends(get_db),
) -> PartyRadarResponse:
    try:
        from uuid import UUID

        entity_uuid = UUID(entity_id)
    except Exception:
        raise HTTPException(status_code=400, detail="entity_id must be party_id (uuid)")

    party = db.get(models.PartyRegistry, entity_uuid)
    if not party or getattr(party, "status", None) == "rejected":
        raise HTTPException(status_code=404, detail="party not found")

    payload = radar_service.build_party_radar(
        db,
        party_id=entity_uuid,
        party_name=getattr(party, "name_ja", None),
        scope=scope,
    )
    return PartyRadarResponse.model_validate(payload)


@router.get("/radar/parties", response_model=list[PartyRadarResponse])
def list_parties_radar(
    scope: str = Query("official", pattern="^(official|mixed)$"),
    include_topics: int = Query(0, ge=0, le=1, description="カテゴリ内のトピック明細も返す(1)か"),
    db: Session = Depends(get_db),
) -> list[PartyRadarResponse]:
    payloads = radar_service.build_all_party_radars(
        db,
        scope=scope,
        include_topics=bool(int(include_topics)),
    )
    return [PartyRadarResponse.model_validate(p) for p in payloads]
