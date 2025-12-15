from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models


def list_topics(db: Session) -> list[models.Topic]:
    return list(db.scalars(select(models.Topic).order_by(models.Topic.topic_id.asc())))


def get_topic(db: Session, topic_id: str) -> models.Topic | None:
    return db.get(models.Topic, topic_id)


def get_active_rubric(db: Session, topic_id: str) -> models.TopicRubric | None:
    rubric = db.scalar(
        select(models.TopicRubric)
        .where(models.TopicRubric.topic_id == topic_id, models.TopicRubric.status == "active")
        .order_by(models.TopicRubric.version.desc())
        .limit(1)
    )
    if rubric:
        return rubric
    return db.scalar(
        select(models.TopicRubric)
        .where(models.TopicRubric.topic_id == topic_id)
        .order_by(models.TopicRubric.version.desc())
        .limit(1)
    )


def get_latest_score_run(db: Session, topic_id: str) -> models.ScoreRun | None:
    return db.scalar(
        select(models.ScoreRun)
        .where(models.ScoreRun.topic_id == topic_id)
        .order_by(models.ScoreRun.created_at.desc())
        .limit(1)
    )


def list_scores_for_run(db: Session, run_id) -> list[models.TopicScore]:
    return list(db.scalars(select(models.TopicScore).where(models.TopicScore.run_id == run_id)))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)

