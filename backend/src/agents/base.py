from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Protocol


class Fetcher(Protocol):
    """HTTPフェッチャの抽象。実運用ではhttpx/requests、検証ではモックを注入する。"""

    def fetch(self, url: str, *, timeout: int = 20) -> str:
        ...


class SearchClient(Protocol):
    """検索クライアントの抽象。政党名と公式ページ候補を返す。"""

    def search_parties(self, query: str) -> List["DiscoveryCandidate"]:
        ...


class PolicyEvidenceClient(Protocol):
    """Web検索/groundingにより、公式ドメイン内の根拠URLと抜粋を返す。"""

    def find_policy_evidence_bulk(
        self,
        *,
        topic: str,
        parties: List["ResolvedParty"],
        max_per_party: int = 3,
    ) -> List["PolicyEvidence"]:
        ...


class LLMClient(Protocol):
    """スコア生成用のLLMクライアント抽象。"""

    def score_policies(self, *, topic: str, party_docs: List["PartyDocs"]) -> List["ScoreResult"]:
        ...


@dataclass
class DiscoveryCandidate:
    name_ja: str
    candidate_url: str
    source: str  # e.g. "search" or "linklist"


@dataclass
class ResolvedParty:
    name_ja: str
    official_url: str
    allowed_domains: List[str]


@dataclass
class PolicyDocument:
    url: str
    content: str


@dataclass
class ScoreResult:
    party_name: str
    stance_label: str
    stance_score: int
    confidence: float
    rationale: str
    evidence_url: str | None = None


@dataclass
class PartyDocs:
    party_name: str
    docs: List[PolicyDocument]


@dataclass
class EvidenceSnippet:
    evidence_url: str
    quote: str


@dataclass
class PolicyEvidence:
    party_name: str
    evidence: List[EvidenceSnippet]


def extract_domain(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).netloc.lower()


def pick_first(iterable: Iterable[str]) -> str | None:
    for item in iterable:
        return item
    return None
