from __future__ import annotations

from typing import List

from .base import DiscoveryCandidate, SearchClient


class DiscoveryAgent:
    """政党候補を検索エンジン等から収集するエージェント。"""

    def __init__(self, search_client: SearchClient):
        self.search_client = search_client

    def run(self, query: str = "政党 公式 サイト") -> List[DiscoveryCandidate]:
        # 現時点では単純に検索結果を返す。将来的に複数ソースをマージする。
        return self.search_client.search_parties(query)
