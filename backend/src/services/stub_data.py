from datetime import datetime
from typing import Dict, List

from ..schemas import Evidence, ScoreItem, ScoreMeta, Topic


topics: List[Topic] = [
    Topic(topic_id="tax", name="税制", description="所得税・法人税・消費税などの方針"),
    Topic(topic_id="defense", name="防衛", description="防衛政策・安全保障に関する立場"),
]

scores_by_topic: Dict[str, List[ScoreItem]] = {
    "tax": [
        ScoreItem(
            entity_type="party",
            entity_id="party-lp",
            topic_id="tax",
            mode="claim",
            stance_label="conditional",
            stance_score=35,
            confidence=0.72,
            rationale="消費税の時限的減税を検討する声明に基づく。",
            evidence=[
                Evidence(
                    url="https://example.jp/policy/tax",
                    fetched_at=datetime.fromisoformat("2025-12-12T03:00:00"),
                    quote="消費税率について経済状況に応じた見直しを行う。",
                    quote_start=1234,
                    quote_end=1301,
                )
            ],
            meta=ScoreMeta(topic_version="2025-12-01", calc_version="2025-12-12T03:30:00Z"),
        )
    ],
    "defense": [
        ScoreItem(
            entity_type="party",
            entity_id="party-dp",
            topic_id="defense",
            mode="claim",
            stance_label="support",
            stance_score=70,
            confidence=0.81,
            rationale="防衛力強化計画への賛同を明示。",
            evidence=[
                Evidence(
                    url="https://example.jp/policy/defense",
                    fetched_at=datetime.fromisoformat("2025-12-10T02:00:00"),
                    quote="防衛予算の増額に賛成する。",
                    quote_start=210,
                    quote_end=230,
                )
            ],
            meta=ScoreMeta(topic_version="2025-12-01", calc_version="2025-12-12T03:30:00Z"),
        )
    ],
}
