import uuid
from datetime import datetime
from enum import Enum
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class PartyStatusEnum(str, Enum):
    candidate = "candidate"
    verified = "verified"
    needs_review = "needs_review"
    rejected = "rejected"


class Evidence(BaseModel):
    url: str
    fetched_at: datetime
    quote: str
    quote_start: int
    quote_end: int
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "url": "https://example.jp/policy/...",
                "fetched_at": "2025-12-12T03:00:00Z",
                "quote": "…抜粋…",
                "quote_start": 1234,
                "quote_end": 1301,
            }
        }
    )


class ScoreMeta(BaseModel):
    topic_version: str
    calc_version: str


class ScoreItem(BaseModel):
    entity_type: Literal["party", "politician"]
    entity_id: str
    topic_id: str
    mode: Literal["claim", "action", "combined"]
    stance_label: Literal["support", "oppose", "conditional", "unknown", "not_mentioned"]
    stance_score: int = Field(..., ge=-100, le=100)
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str
    evidence: List[Evidence]
    meta: ScoreMeta
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "entity_type": "party",
                "entity_id": "party-lp",
                "topic_id": "tax",
                "mode": "claim",
                "stance_label": "conditional",
                "stance_score": 35,
                "confidence": 0.72,
                "rationale": "根拠抜粋に基づく要約",
                "evidence": [
                    {
                        "url": "https://example.jp/policy/...",
                        "fetched_at": "2025-12-12T03:00:00Z",
                        "quote": "…抜粋…",
                        "quote_start": 1234,
                        "quote_end": 1301,
                    }
                ],
                "meta": {
                    "topic_version": "2025-12-01",
                    "calc_version": "2025-12-12T03:30:00Z",
                },
            }
        }
    )


class Topic(BaseModel):
    topic_id: str
    name: str
    description: Optional[str] = None
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"topic_id": "tax", "name": "税制", "description": "所得税・法人税・消費税などの方針"}
        }
    )


# Party registry schemas
class PartyBase(BaseModel):
    name_ja: str
    name_en: Optional[str] = None
    official_home_url: Optional[str] = None
    allowed_domains: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    status: PartyStatusEnum = PartyStatusEnum.candidate


class PartyCreate(PartyBase):
    evidence: Any = Field(default_factory=dict)


class PartyResponse(PartyBase):
    party_id: uuid.UUID
    evidence: Any = Field(default_factory=dict)
    first_seen_at: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TopicsResponse(BaseModel):
    topics: List[Topic]


class TopicPositionsResponse(BaseModel):
    topic: Topic
    mode: Literal["claim", "action", "combined"]
    entity: Literal["party", "party+politician"]
    scores: List[ScoreItem]


class TopicDetailResponse(BaseModel):
    topic: Topic
    mode: Literal["claim", "action", "combined"]
    entity_id: str
    score: ScoreItem


class AdminJobResponse(BaseModel):
    status: str = "queued"
    detail: str


class RubricStatusEnum(str, Enum):
    draft = "draft"
    active = "active"
    archived = "archived"


class RubricStep(BaseModel):
    score: int = Field(..., ge=-100, le=100)
    label: str
    criteria: str


class TopicCreate(BaseModel):
    topic_id: str
    name: str
    description: Optional[str] = None


class TopicRubricCreate(BaseModel):
    axis_a_label: str
    axis_b_label: str
    steps: List[RubricStep]
    status: RubricStatusEnum = RubricStatusEnum.draft


class TopicRubricUpdate(BaseModel):
    axis_a_label: Optional[str] = None
    axis_b_label: Optional[str] = None
    steps: Optional[List[RubricStep]] = None
    status: Optional[RubricStatusEnum] = None


class TopicRubricResponse(BaseModel):
    rubric_id: uuid.UUID
    topic_id: str
    version: int
    status: RubricStatusEnum
    axis_a_label: str
    axis_b_label: str
    steps: List[RubricStep]
    generated_by: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    prompt_version: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class TopicRubricGenerateRequest(BaseModel):
    topic_name: str
    description: Optional[str] = None
    # 軸のヒント（任意）
    axis_a_hint: Optional[str] = None
    axis_b_hint: Optional[str] = None
    # 生成する段階数（推奨: 5）
    steps_count: int = Field(default=5, ge=3, le=9)


class TopicRubricGenerateResponse(BaseModel):
    topic: TopicCreate
    rubric: TopicRubricResponse
