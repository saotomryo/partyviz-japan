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
    entity_name: Optional[str] = None
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
    is_active: Optional[bool] = True
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


class PartyUpdate(BaseModel):
    name_ja: Optional[str] = None
    name_en: Optional[str] = None
    official_home_url: Optional[str] = None
    allowed_domains: Optional[List[str]] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    status: Optional[PartyStatusEnum] = None
    evidence: Optional[Any] = None


class PolicySourceItem(BaseModel):
    base_url: str
    status: str = "active"


class PolicySourceList(BaseModel):
    party_id: uuid.UUID
    sources: List[PolicySourceItem]


class PolicySourceUpdate(BaseModel):
    base_urls: List[str] = Field(default_factory=list)


class PartyRegistryDiscoverRequest(BaseModel):
    query: str = Field(
        default="日本の国政政党（国会に議席のある政党）と主要な新党・政治団体の公式サイト一覧 チームみらい",
    )
    limit: int = Field(default=50, ge=1, le=200)
    provider: Literal["auto", "gemini", "openai"] = "auto"
    openai_model: Optional[str] = None
    gemini_model: Optional[str] = None
    dry_run: bool = False


class PartyRegistryDiscoverItem(BaseModel):
    action: Literal["created", "updated", "skipped"]
    name_ja: str
    official_home_url: str | None = None


class PartyRegistryDiscoverResponse(BaseModel):
    query: str
    provider: str
    found: int
    created: int
    updated: int
    skipped: int
    results: List[PartyRegistryDiscoverItem]


class AdminPurgeRequest(BaseModel):
    targets: List[Literal["parties", "topics", "events", "policy", "scores", "all"]] = Field(
        default_factory=lambda: ["all"]
    )
    confirm: str
    dry_run: bool = False


class AdminPurgeResponse(BaseModel):
    deleted: dict[str, int]


class TopicScoreRunRequest(BaseModel):
    topic_text: Optional[str] = None
    search_provider: Literal["auto", "gemini", "openai"] = "auto"
    score_provider: Literal["auto", "gemini", "openai"] = "auto"
    search_openai_model: Optional[str] = None
    search_gemini_model: Optional[str] = None
    score_openai_model: Optional[str] = None
    score_gemini_model: Optional[str] = None
    max_parties: Optional[int] = Field(default=None, ge=1, le=200)
    max_evidence_per_party: int = Field(default=2, ge=1, le=5)
    include_external: bool = Field(default=False, description="公式ページ以外のWebページも根拠に含めたスコア（mixed）を追加で保存する")
    index_only: bool = Field(default=False, description="公式の政策インデックスのみでスコアリング（検索ベースを使わない）")


class TopicScoreItem(BaseModel):
    party_id: uuid.UUID
    name_ja: str
    stance_label: str
    stance_score: int
    confidence: float
    rationale: str
    evidence_url: Optional[str] = None
    evidence_quote: Optional[str] = None


class TopicScoreRunResponse(BaseModel):
    run_id: uuid.UUID
    topic_id: str
    created_at: Optional[datetime] = None
    search_provider: Optional[str] = None
    search_model: Optional[str] = None
    score_provider: Optional[str] = None
    score_model: Optional[str] = None
    scores: List[TopicScoreItem]
    model_config = ConfigDict(from_attributes=True)


class TopicsResponse(BaseModel):
    topics: List[Topic]


class TopicPositionsResponse(BaseModel):
    topic: Topic
    mode: Literal["claim", "action", "combined"]
    entity: Literal["party", "party+politician"]
    rubric_version: Optional[int] = None
    axis_a_label: Optional[str] = None
    axis_b_label: Optional[str] = None
    run_id: Optional[uuid.UUID] = None
    run_created_at: Optional[datetime] = None
    run_scope: Optional[str] = None
    run_meta: Optional[dict] = None
    scores: List[ScoreItem]


class TopicDetailResponse(BaseModel):
    topic: Topic
    mode: Literal["claim", "action", "combined"]
    entity_id: str
    rubric_version: Optional[int] = None
    axis_a_label: Optional[str] = None
    axis_b_label: Optional[str] = None
    score: ScoreItem


class RadarTopicContribution(BaseModel):
    topic_id: str
    topic_name: str
    stance_score: int = Field(..., ge=-100, le=100)
    stance_label: str
    confidence: float = Field(..., ge=0.0, le=1.0)


class RadarCategoryResult(BaseModel):
    key: str
    label: str
    count: int = Field(..., ge=0)
    median: Optional[float] = Field(default=None, ge=-100, le=100)
    min: Optional[int] = Field(default=None, ge=-100, le=100)
    max: Optional[int] = Field(default=None, ge=-100, le=100)
    topics: List[RadarTopicContribution] = Field(default_factory=list)


class PartyRadarResponse(BaseModel):
    entity_type: Literal["party"] = "party"
    entity_id: str
    entity_name: Optional[str] = None
    scope: Literal["official", "mixed"]
    topic_total: int = Field(..., ge=0)
    topic_included: int = Field(..., ge=0)
    categories: List[RadarCategoryResult]


class PartySummaryResponse(BaseModel):
    entity_id: str
    entity_name: str
    scope: Literal["official", "mixed"]
    summary_text: str
    positive_topics: List[str] = Field(default_factory=list)
    negative_topics: List[str] = Field(default_factory=list)
    near_party: Optional[str] = None
    far_party: Optional[str] = None
    evidence_quote: Optional[str] = None


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
    search_subkeywords: List[str] = Field(default_factory=list)
    is_active: Optional[bool] = True
    model_config = ConfigDict(from_attributes=True)


class TopicCreateRequest(BaseModel):
    """topic_id を省略したトピック作成用（管理UI向け）。"""

    name: str
    description: Optional[str] = None
    topic_id: Optional[str] = None
    is_active: Optional[bool] = True


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
    provider: Literal["auto", "gemini", "openai"] = "auto"
    openai_model: Optional[str] = None
    gemini_model: Optional[str] = None
    # 軸のヒント（任意）
    axis_a_hint: Optional[str] = None
    axis_b_hint: Optional[str] = None
    # 生成する段階数（推奨: 5）
    steps_count: int = Field(default=5, ge=3, le=9)


class TopicRubricGenerateResponse(BaseModel):
    topic: TopicCreate
    rubric: TopicRubricResponse
