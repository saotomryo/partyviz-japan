from __future__ import annotations

from typing import List, Optional

from sqlalchemy import and_, func, select, update
from sqlalchemy.orm import Session

from ..db import models
from ..schemas import TopicCreate, TopicRubricCreate, TopicRubricUpdate
from ..settings import settings
from ..agents import query_expander


def _generate_subkeywords(name: str, description: str | None) -> list[str]:
    topic_text = name.strip()
    if description and description.strip():
        topic_text = f"{topic_text}\n{description.strip()}"
    # Prefer Gemini for cost; fallback to OpenAI.
    if settings.gemini_api_key:
        return query_expander.generate_subkeywords_gemini(
            api_key=settings.gemini_api_key,
            model=settings.gemini_score_model,
            topic=topic_text,
        )
    if settings.openai_api_key:
        return query_expander.generate_subkeywords_openai(
            api_key=settings.openai_api_key,
            model=settings.openai_score_model,
            topic=topic_text,
        )
    return []


def upsert_topic(db: Session, payload: TopicCreate) -> models.Topic:
    topic = db.get(models.Topic, payload.topic_id)
    if topic:
        topic.name = payload.name
        topic.description = payload.description
        topic.is_active = True if payload.is_active is None else bool(payload.is_active)
        topic.search_subkeywords = _generate_subkeywords(payload.name, payload.description)
        db.commit()
        db.refresh(topic)
        return topic

    topic = models.Topic(topic_id=payload.topic_id, name=payload.name, description=payload.description)
    topic.is_active = True if payload.is_active is None else bool(payload.is_active)
    topic.search_subkeywords = _generate_subkeywords(payload.name, payload.description)
    db.add(topic)
    db.commit()
    db.refresh(topic)
    return topic


def get_topic(db: Session, topic_id: str) -> Optional[models.Topic]:
    return db.get(models.Topic, topic_id)


def list_topics(db: Session) -> List[models.Topic]:
    stmt = select(models.Topic).order_by(models.Topic.topic_id.asc())
    return list(db.scalars(stmt))


def _next_version(db: Session, topic_id: str) -> int:
    stmt = select(func.coalesce(func.max(models.TopicRubric.version), 0)).where(models.TopicRubric.topic_id == topic_id)
    return int(db.scalar(stmt) or 0) + 1


def create_rubric(db: Session, topic_id: str, payload: TopicRubricCreate, *, meta: dict | None = None) -> models.TopicRubric:
    version = _next_version(db, topic_id)
    rubric = models.TopicRubric(
        topic_id=topic_id,
        version=version,
        status=payload.status.value,
        axis_a_label=payload.axis_a_label,
        axis_b_label=payload.axis_b_label,
        steps=[s.model_dump() for s in payload.steps],
        generated_by=(meta or {}).get("generated_by"),
        llm_provider=(meta or {}).get("llm_provider"),
        llm_model=(meta or {}).get("llm_model"),
        prompt_version=(meta or {}).get("prompt_version"),
    )
    db.add(rubric)
    db.commit()
    db.refresh(rubric)
    return rubric


def list_rubrics(db: Session, topic_id: str) -> List[models.TopicRubric]:
    stmt = select(models.TopicRubric).where(models.TopicRubric.topic_id == topic_id).order_by(models.TopicRubric.version.desc())
    return list(db.scalars(stmt))


def get_rubric(db: Session, rubric_id) -> Optional[models.TopicRubric]:
    return db.get(models.TopicRubric, rubric_id)


def update_rubric(db: Session, rubric_id, payload: TopicRubricUpdate) -> models.TopicRubric:
    rubric = db.get(models.TopicRubric, rubric_id)
    if not rubric:
        raise ValueError("rubric not found")

    if payload.axis_a_label is not None:
        rubric.axis_a_label = payload.axis_a_label
    if payload.axis_b_label is not None:
        rubric.axis_b_label = payload.axis_b_label
    if payload.steps is not None:
        rubric.steps = [s.model_dump() for s in payload.steps]
    if payload.status is not None:
        rubric.status = payload.status.value

    db.commit()
    db.refresh(rubric)
    return rubric


def activate_rubric(db: Session, rubric_id) -> models.TopicRubric:
    rubric = db.get(models.TopicRubric, rubric_id)
    if not rubric:
        raise ValueError("rubric not found")

    # 同一topicのactiveをarchivedへ
    db.execute(
        update(models.TopicRubric)
        .where(and_(models.TopicRubric.topic_id == rubric.topic_id, models.TopicRubric.status == "active"))
        .values(status="archived")
    )
    rubric.status = "active"
    db.commit()
    db.refresh(rubric)
    return rubric
