from __future__ import annotations

from typing import List

from .base import LLMClient, PartyDocs, ScoreResult


class ScoringAgent:
    """複数政党のドキュメントをまとめてLLMに渡し、相対スコアを算出するエージェント。"""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    def score(self, *, topic: str, party_docs: List[PartyDocs]) -> List[ScoreResult]:
        return self.llm_client.score_policies(topic=topic, party_docs=party_docs)
