from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..schemas import (
    AdminJobResponse,
    PartyCreate,
    PartyResponse,
    TopicCreate,
    TopicRubricCreate,
    TopicRubricGenerateRequest,
    TopicRubricGenerateResponse,
    TopicRubricResponse,
    TopicRubricUpdate,
)
from ..services import party_registry
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


@router.get("/topics", response_model=list[TopicCreate], dependencies=[Depends(require_api_key)])
def admin_list_topics(db: Session = Depends(get_db)) -> list[TopicCreate]:
    return [TopicCreate(topic_id=t.topic_id, name=t.name, description=t.description) for t in topic_rubrics.list_topics(db)]


@router.put("/topics/{topic_id}", response_model=TopicCreate, dependencies=[Depends(require_api_key)])
def admin_upsert_topic(topic_id: str, payload: TopicCreate, db: Session = Depends(get_db)) -> TopicCreate:
    if payload.topic_id != topic_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="topic_id mismatch")
    t = topic_rubrics.upsert_topic(db, payload)
    return TopicCreate(topic_id=t.topic_id, name=t.name, description=t.description)


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
    provider = (settings.agent_search_provider or "auto").lower()
    # rubric生成はスコアリング寄りなので agent_score_provider を優先
    provider = (settings.agent_score_provider or provider or "auto").lower()

    draft = None
    if provider in {"auto", "gemini"} and settings.gemini_api_key:
        draft = rubric_generator.generate_rubric_gemini(
            api_key=settings.gemini_api_key,
            model=settings.gemini_score_model,
            topic_name=req.topic_name,
            description=req.description,
            axis_a_hint=req.axis_a_hint,
            axis_b_hint=req.axis_b_hint,
            steps_count=req.steps_count,
        )
    elif provider in {"auto", "openai"} and settings.openai_api_key:
        draft = rubric_generator.generate_rubric_openai(
            api_key=settings.openai_api_key,
            model=settings.openai_score_model,
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
