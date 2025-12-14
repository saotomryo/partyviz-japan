from __future__ import annotations

from typing import List

from .base import DiscoveryCandidate, ResolvedParty, extract_domain


class ResolutionAgent:
    """候補URLから公式URLを確定し、allowlistを作る。"""

    def __init__(self, fetcher):
        self.fetcher = fetcher

    def resolve(self, candidate: DiscoveryCandidate) -> ResolvedParty:
        # PoC: そのまま到達可能とみなす。実運用では到達確認とリダイレクト追跡を行う。
        domain = extract_domain(candidate.candidate_url)
        allowed = [domain] if domain else []
        return ResolvedParty(name_ja=candidate.name_ja, official_url=candidate.candidate_url, allowed_domains=allowed)

    def resolve_many(self, candidates: List[DiscoveryCandidate]) -> List[ResolvedParty]:
        return [self.resolve(c) for c in candidates]
