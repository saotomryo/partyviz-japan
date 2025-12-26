import re
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..db import models
from ..schemas import (
    AdminJobResponse,
    AdminPurgeRequest,
    AdminPurgeResponse,
    PartyCreate,
    PartyUpdate,
    PartyRegistryDiscoverRequest,
    PartyRegistryDiscoverResponse,
    PartyResponse,
    PolicySourceList,
    PolicySourceUpdate,
    TopicCreate,
    TopicCreateRequest,
    TopicRubricCreate,
    TopicRubricGenerateRequest,
    TopicRubricGenerateResponse,
    TopicRubricResponse,
    TopicRubricUpdate,
    TopicScoreRunRequest,
    TopicScoreRunResponse,
    TopicScoreItem,
)
from ..services import admin_purge as admin_purge_service
from ..services import party_registry
from ..services import party_registry_auto
from ..services import policy_sources
from ..services import policy_crawler
from ..services import scoring_runs
from ..services import snapshot_export
from ..settings import settings
from ..services import topic_rubrics
from ..agents import rubric_generator


router = APIRouter()


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """管理API用の簡易APIキー認証。settings.admin_api_key が未設定なら無効化。"""
    if settings.admin_api_key is None:
        return  # 未設定なら認証スキップ（開発用）
    if x_api_key != settings.admin_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def _generate_topic_id(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9_]+", "_", name.strip().lower()).strip("_")
    if not base:
        base = f"topic_{uuid.uuid4().hex[:8]}"
    if not re.match(r"^[a-z][a-z0-9_]*$", base):
        base = f"topic_{base}"

    candidate = base
    i = 2
    while topic_rubrics.get_topic(db, candidate) is not None:
        candidate = f"{base}_{i}"
        i += 1
    return candidate


@router.post("/discovery/run", response_model=AdminJobResponse, dependencies=[Depends(require_api_key)])
def run_discovery() -> AdminJobResponse:
    return AdminJobResponse(detail="discovery job enqueued (stub)")


@router.post("/resolve/run", response_model=AdminJobResponse, dependencies=[Depends(require_api_key)])
def run_resolution() -> AdminJobResponse:
    return AdminJobResponse(detail="resolution job enqueued (stub)")


@router.post("/crawl/run", response_model=AdminJobResponse, dependencies=[Depends(require_api_key)])
def run_crawl() -> AdminJobResponse:
    return AdminJobResponse(detail="crawl job enqueued (stub)")


@router.post("/score/run", response_model=AdminJobResponse, dependencies=[Depends(require_api_key)])
def run_score() -> AdminJobResponse:
    return AdminJobResponse(detail="score job enqueued (stub)")


@router.get("/parties", response_model=list[PartyResponse], dependencies=[Depends(require_api_key)])
def get_parties(db: Session = Depends(get_db)) -> list[PartyResponse]:
    return party_registry.list_parties(db)


@router.post("/parties", response_model=PartyResponse, dependencies=[Depends(require_api_key)])
def post_party(payload: PartyCreate, db: Session = Depends(get_db)) -> PartyResponse:
    return party_registry.create_party(db, payload)


@router.get("/parties/{party_id}", response_model=PartyResponse, dependencies=[Depends(require_api_key)])
def get_party(party_id: str, db: Session = Depends(get_db)) -> PartyResponse:
    party = party_registry.get_party(db, party_id)
    if not party:
        raise HTTPException(status_code=404, detail="party not found")
    return party


@router.patch("/parties/{party_id}", response_model=PartyResponse, dependencies=[Depends(require_api_key)])
def patch_party(party_id: str, payload: PartyUpdate, db: Session = Depends(get_db)) -> PartyResponse:
    try:
        return party_registry.update_party(db, party_id, payload)
    except ValueError:
        raise HTTPException(status_code=404, detail="party not found")


@router.get("/parties/{party_id}/policy-sources", response_model=PolicySourceList, dependencies=[Depends(require_api_key)])
def get_policy_sources(party_id: str, db: Session = Depends(get_db)) -> PolicySourceList:
    party = db.get(models.PartyRegistry, party_id)
    if not party:
        raise HTTPException(status_code=404, detail="party not found")
    sources = policy_sources.list_sources(db, party_id)
    return PolicySourceList(
        party_id=party.party_id,
        sources=[{"base_url": s.base_url, "status": s.status} for s in sources],
    )


@router.put("/parties/{party_id}/policy-sources", response_model=PolicySourceList, dependencies=[Depends(require_api_key)])
def put_policy_sources(party_id: str, payload: PolicySourceUpdate, db: Session = Depends(get_db)) -> PolicySourceList:
    try:
        sources = policy_sources.replace_sources(db, party_id, payload.base_urls)
    except ValueError:
        raise HTTPException(status_code=404, detail="party not found")
    return PolicySourceList(
        party_id=party_id,
        sources=[{"base_url": s.base_url, "status": s.status} for s in sources],
    )


@router.post("/parties/{party_id}/policy-sources/crawl", dependencies=[Depends(require_api_key)])
def crawl_policy_sources(party_id: str, max_urls: int = 200, max_depth: int = 2, db: Session = Depends(get_db)) -> dict:
    try:
        stats = policy_crawler.crawl_party_policy_sources(
            db,
            party_id=party_id,
            max_urls=max(1, min(int(max_urls), 500)),
            max_depth=max(0, min(int(max_depth), 4)),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"party_id": party_id, "stats": stats.__dict__}


@router.post("/parties/discover", response_model=PartyRegistryDiscoverResponse, dependencies=[Depends(require_api_key)])
def discover_parties(req: PartyRegistryDiscoverRequest, db: Session = Depends(get_db)) -> PartyRegistryDiscoverResponse:
    used_provider, results, summary = party_registry_auto.discover_and_upsert_parties(
        db,
        query=req.query,
        provider=req.provider,
        openai_model=req.openai_model,
        gemini_model=req.gemini_model,
        limit=req.limit,
        dry_run=req.dry_run,
        debug=settings.agent_debug,
    )
    return PartyRegistryDiscoverResponse(
        query=req.query,
        provider=used_provider,
        found=int(summary.get("found", 0)),
        created=int(summary.get("created", 0)),
        updated=int(summary.get("updated", 0)),
        skipped=int(summary.get("skipped", 0)),
        results=results,
    )


@router.get("/snapshot", dependencies=[Depends(require_api_key)])
def export_snapshot(db: Session = Depends(get_db)):
    """公開用のスナップショットJSON（静的ホスティング向け）。"""
    return snapshot_export.build_snapshot(db)

@router.post("/dev/purge", response_model=AdminPurgeResponse, dependencies=[Depends(require_api_key)])
def admin_purge_endpoint(req: AdminPurgeRequest, db: Session = Depends(get_db)) -> AdminPurgeResponse:
    if settings.admin_api_key is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ADMIN_API_KEY must be set to use purge endpoint",
        )
    if req.confirm != "DELETE":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="confirm must be 'DELETE'")
    result = admin_purge_service.purge(db, targets=req.targets, dry_run=req.dry_run)
    return AdminPurgeResponse(deleted=result.deleted)


@router.get("/topics", response_model=list[TopicCreate], dependencies=[Depends(require_api_key)])
def admin_list_topics(db: Session = Depends(get_db)) -> list[TopicCreate]:
    return [
        TopicCreate(
            topic_id=t.topic_id,
            name=t.name,
            description=t.description,
            search_subkeywords=list(getattr(t, "search_subkeywords", None) or []),
        )
        for t in topic_rubrics.list_topics(db)
    ]


@router.post("/topics", response_model=TopicCreate, dependencies=[Depends(require_api_key)])
def admin_create_topic(payload: TopicCreateRequest, db: Session = Depends(get_db)) -> TopicCreate:
    topic_id = payload.topic_id or _generate_topic_id(db, payload.name)
    t = topic_rubrics.upsert_topic(db, TopicCreate(topic_id=topic_id, name=payload.name, description=payload.description))
    return TopicCreate(topic_id=t.topic_id, name=t.name, description=t.description, search_subkeywords=list(getattr(t, "search_subkeywords", None) or []))


@router.put("/topics/{topic_id}", response_model=TopicCreate, dependencies=[Depends(require_api_key)])
def admin_upsert_topic(topic_id: str, payload: TopicCreate, db: Session = Depends(get_db)) -> TopicCreate:
    if payload.topic_id != topic_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="topic_id mismatch")
    t = topic_rubrics.upsert_topic(db, payload)
    return TopicCreate(topic_id=t.topic_id, name=t.name, description=t.description, search_subkeywords=list(getattr(t, "search_subkeywords", None) or []))


@router.get("/topics/{topic_id}/rubrics", response_model=list[TopicRubricResponse], dependencies=[Depends(require_api_key)])
def admin_list_rubrics(topic_id: str, db: Session = Depends(get_db)) -> list[TopicRubricResponse]:
    return topic_rubrics.list_rubrics(db, topic_id)


@router.post("/topics/{topic_id}/rubrics", response_model=TopicRubricResponse, dependencies=[Depends(require_api_key)])
def admin_create_rubric(topic_id: str, payload: TopicRubricCreate, db: Session = Depends(get_db)) -> TopicRubricResponse:
    if not topic_rubrics.get_topic(db, topic_id):
        raise HTTPException(status_code=404, detail="topic not found")
    return topic_rubrics.create_rubric(db, topic_id, payload)


@router.patch("/rubrics/{rubric_id}", response_model=TopicRubricResponse, dependencies=[Depends(require_api_key)])
def admin_update_rubric(rubric_id: str, payload: TopicRubricUpdate, db: Session = Depends(get_db)) -> TopicRubricResponse:
    try:
        return topic_rubrics.update_rubric(db, rubric_id, payload)
    except ValueError:
        raise HTTPException(status_code=404, detail="rubric not found")


@router.post("/rubrics/{rubric_id}/activate", response_model=TopicRubricResponse, dependencies=[Depends(require_api_key)])
def admin_activate_rubric(rubric_id: str, db: Session = Depends(get_db)) -> TopicRubricResponse:
    try:
        return topic_rubrics.activate_rubric(db, rubric_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="rubric not found")


@router.post(
    "/topics/{topic_id}/rubrics/generate",
    response_model=TopicRubricGenerateResponse,
    dependencies=[Depends(require_api_key)],
)
def admin_generate_rubric(topic_id: str, req: TopicRubricGenerateRequest, db: Session = Depends(get_db)) -> TopicRubricGenerateResponse:
    # 生成AIでドラフト作成 → DBにdraft保存（人が編集可能）
    provider = (req.provider or "auto").lower()
    if provider == "auto":
        provider = (settings.agent_search_provider or "auto").lower()
        # rubric生成はスコアリング寄りなので agent_score_provider を優先
        provider = (settings.agent_score_provider or provider or "auto").lower()

    draft = None
    if provider in {"auto", "gemini"} and settings.gemini_api_key:
        draft = rubric_generator.generate_rubric_gemini(
            api_key=settings.gemini_api_key,
            model=req.gemini_model or settings.gemini_score_model,
            topic_name=req.topic_name,
            description=req.description,
            axis_a_hint=req.axis_a_hint,
            axis_b_hint=req.axis_b_hint,
            steps_count=req.steps_count,
        )
    elif provider in {"auto", "openai"} and settings.openai_api_key:
        draft = rubric_generator.generate_rubric_openai(
            api_key=settings.openai_api_key,
            model=req.openai_model or settings.openai_score_model,
            topic_name=req.topic_name,
            description=req.description,
            axis_a_hint=req.axis_a_hint,
            axis_b_hint=req.axis_b_hint,
            steps_count=req.steps_count,
        )
    else:
        raise HTTPException(status_code=400, detail="No available LLM provider for rubric generation")

    topic_payload = TopicCreate(topic_id=topic_id, name=req.topic_name, description=req.description)
    topic_rubrics.upsert_topic(db, topic_payload)

    rubric_payload = TopicRubricCreate(
        axis_a_label=draft.axis_a_label,
        axis_b_label=draft.axis_b_label,
        steps=[
            {"score": int(s["score"]), "label": str(s["label"]), "criteria": str(s["criteria"])}
            for s in draft.steps
        ],
    )
    created = topic_rubrics.create_rubric(
        db,
        topic_id,
        rubric_payload,
        meta={
            "generated_by": "llm",
            "llm_provider": draft.llm_provider,
            "llm_model": draft.llm_model,
            "prompt_version": draft.prompt_version,
        },
    )

    return TopicRubricGenerateResponse(topic=topic_payload, rubric=created)


@router.post("/topics/{topic_id}/scores/run", response_model=TopicScoreRunResponse, dependencies=[Depends(require_api_key)])
def admin_run_topic_scoring(topic_id: str, req: TopicScoreRunRequest, db: Session = Depends(get_db)) -> TopicScoreRunResponse:
    topic = topic_rubrics.get_topic(db, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")
    topic_text = req.topic_text or topic.name
    try:
        run = scoring_runs.run_topic_scoring(
            db,
            topic_id=topic_id,
            topic_text=topic_text,
            scope="official",
            search_provider=req.search_provider,
            search_openai_model=req.search_openai_model,
            search_gemini_model=req.search_gemini_model,
            score_provider=req.score_provider,
            score_openai_model=req.score_openai_model,
            score_gemini_model=req.score_gemini_model,
            max_parties=req.max_parties,
            max_evidence_per_party=req.max_evidence_per_party,
            index_only=req.index_only,
            debug=settings.agent_debug,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not req.index_only and req.include_external:
        try:
            scoring_runs.run_topic_scoring(
                db,
                topic_id=topic_id,
                topic_text=topic_text,
                scope="mixed",
                search_provider=req.search_provider,
                search_openai_model=req.search_openai_model,
                search_gemini_model=req.search_gemini_model,
                score_provider=req.score_provider,
                score_openai_model=req.score_openai_model,
                score_gemini_model=req.score_gemini_model,
                max_parties=req.max_parties,
                max_evidence_per_party=req.max_evidence_per_party,
                index_only=req.index_only,
                debug=settings.agent_debug,
            )
        except ValueError:
            pass

    scores = list(db.scalars(select(models.TopicScore).where(models.TopicScore.run_id == run.run_id)))
    party_map = {p.party_id: p for p in party_registry.list_parties(db)}
    return TopicScoreRunResponse(
        run_id=run.run_id,
        topic_id=topic_id,
        created_at=run.created_at,
        search_provider=run.search_provider,
        search_model=run.search_model,
        score_provider=run.score_provider,
        score_model=run.score_model,
        scores=[
            TopicScoreItem(
                party_id=s.party_id,
                name_ja=(party_map.get(s.party_id).name_ja if party_map.get(s.party_id) else ""),
                stance_label=s.stance_label,
                stance_score=int(s.stance_score),
                confidence=float(s.confidence),
                rationale=s.rationale,
                evidence_url=s.evidence_url,
                evidence_quote=s.evidence_quote,
            )
            for s in scores
        ],
    )


@router.get("/topics/{topic_id}/scores/latest", response_model=TopicScoreRunResponse, dependencies=[Depends(require_api_key)])
def admin_get_latest_topic_scoring(topic_id: str, db: Session = Depends(get_db)) -> TopicScoreRunResponse:
    run, scores = scoring_runs.list_latest_topic_scores(db, topic_id=topic_id)
    if not run:
        raise HTTPException(status_code=404, detail="no score run")
    party_map = {p.party_id: p for p in party_registry.list_parties(db)}
    return TopicScoreRunResponse(
        run_id=run.run_id,
        topic_id=topic_id,
        created_at=run.created_at,
        search_provider=run.search_provider,
        search_model=run.search_model,
        score_provider=run.score_provider,
        score_model=run.score_model,
        scores=[
            TopicScoreItem(
                party_id=s.party_id,
                name_ja=(party_map.get(s.party_id).name_ja if party_map.get(s.party_id) else ""),
                stance_label=s.stance_label,
                stance_score=int(s.stance_score),
                confidence=float(s.confidence),
                rationale=s.rationale,
                evidence_url=s.evidence_url,
                evidence_quote=s.evidence_quote,
            )
            for s in scores
        ],
    )
