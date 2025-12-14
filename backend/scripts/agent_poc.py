"""
シンプルなエージェントPoC:
- 検索クライアント: ダミーで政党候補を返す
- フェッチャ: URLに応じたダミーHTML/テキストを返す
- LLMクライアント: テキスト長とキーワードで簡易スコア

実行例:
    python backend/scripts/agent_poc.py --topic 税制 --keyword 税
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from pprint import pprint

# Ensure project root (backend/) is on sys.path so that `src` can be imported when running as a script
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.agents.base import DiscoveryCandidate, PartyDocs, ScoreResult
from src.agents.crawler import CrawlerAgent
from src.agents.discovery import DiscoveryAgent
from src.agents.fetchers import HttpxFetcher
from src.agents.llm_clients import GeminiLLMClient, OpenAILLMClient
from src.agents.llm_search import GeminiLLMSearchClient, OpenAILLMSearchClient
from src.agents.resolution import ResolutionAgent
from src.agents.scorer import ScoringAgent
from src.settings import settings


# ---- Dummy implementations (オフライン検証用) ------------------


class DummySearchClient:
    def search_parties(self, query: str):
        return [
            DiscoveryCandidate(name_ja="テスト党A", candidate_url="https://party-a.example.com", source="dummy"),
            DiscoveryCandidate(name_ja="テスト党B", candidate_url="https://party-b.example.com", source="dummy"),
        ]


class DummyFetcher:
    def fetch(self, url: str, *, timeout: int = 20) -> str:
        # URLごとに政策キーワードを含むコンテンツを返す
        if "party-a" in url:
            return "税制 政策として消費税の段階的引き下げを検討する。"
        if "party-b" in url:
            return "防衛政策の見直し。税については据え置き。"
        return "政策方針。"


class DummyLLM:
    def score_policies(self, *, topic: str, party_docs: list[PartyDocs]) -> list[ScoreResult]:
        # 相対評価: コンテンツ長とキーワードヒット数でスコアを分配する単純ロジック
        scores: list[ScoreResult] = []
        max_len = max((sum(len(doc.content) for doc in p.docs) for p in party_docs), default=1)
        for pd in party_docs:
            total_len = sum(len(doc.content) for doc in pd.docs)
            topic_hits = sum(1 for doc in pd.docs if topic in doc.content)
            stance = int((total_len / max_len) * 80) + (topic_hits * 10)
            stance = max(-100, min(100, stance))
            label = "support" if stance > 50 else "conditional" if stance > 10 else "not_mentioned"
            conf = 0.5 + 0.5 * (topic_hits / max(1, len(pd.docs)))
            rationale = f"len_ratio={total_len}/{max_len}, topic_hits={topic_hits}"
            # 最長コンテンツのURLを根拠に設定
            evidence_url = None
            if pd.docs:
                evidence_url = max(pd.docs, key=lambda d: len(d.content)).url
            scores.append(
                ScoreResult(
                    party_name=pd.party_name,
                    stance_label=label,
                    stance_score=stance,
                    confidence=min(conf, 1.0),
                    rationale=rationale,
                    evidence_url=evidence_url,
                )
            )
        return scores


# ---- Runner ----------------------------------------------------


def run(topic: str, keyword: str):
    # 切り替え: USE_DUMMY_AGENTS=true ならダミー、false なら実処理（LLM検索＋HTTPフェッチ）
    use_dummy = settings.use_dummy_agents

    if use_dummy:
        print("ダミーエージェントを使用します。")
        discovery = DiscoveryAgent(DummySearchClient())
        fetcher = DummyFetcher()
    else:
        print("実エージェントを使用します。OPENAI_API_KEY または GEMINI_API_KEY が必要です。")
        if settings.openai_api_key:
            search_client = OpenAILLMSearchClient(api_key=settings.openai_api_key)
            search_client_name = "OpenAILLMSearchClient"
        elif settings.gemini_api_key:
            search_client = GeminiLLMSearchClient(api_key=settings.gemini_api_key)
            search_client_name = "GeminiLLMSearchClient"
        else:
            raise RuntimeError("OPENAI_API_KEY または GEMINI_API_KEY を設定してください")

        print("検索クライアント:", search_client_name)
        discovery = DiscoveryAgent(search_client)
        print("HTTPクライアント: httpx")
        fetcher = HttpxFetcher()

    resolution = ResolutionAgent(fetcher)
    crawler = CrawlerAgent(fetcher)

    if use_dummy:
        llm_client = DummyLLM()
    else:
        if settings.openai_api_key:
            llm_client = OpenAILLMClient(api_key=settings.openai_api_key)
        elif settings.gemini_api_key:
            llm_client = GeminiLLMClient(api_key=settings.gemini_api_key)
        else:
            raise RuntimeError("OPENAI_API_KEY または GEMINI_API_KEY を設定してください")
    scorer = ScoringAgent(llm_client)

    candidates = discovery.run()
    parties = resolution.resolve_many(candidates)
    keywords = [keyword]

    print(f"Topic: {topic}, keywords: {keywords}")
    print("=== Discovery results ===")
    if parties:
        pprint(parties)
    else:
        print("No parties found.")

    print("=== Crawl results ===")
    party_docs = [crawler.crawl(p, keywords=keywords) for p in parties]
    if party_docs:
        for pd in party_docs:
            print(f"{pd.party_name}: {len(pd.docs)} docs")
            for d in pd.docs:
                print(f"  - {d.url} (len={len(d.content)})")
    else:
        print("No documents collected.")

    print("=== Scoring results ===")
    scores = scorer.score(topic=topic, party_docs=party_docs)
    if scores:
        for s in scores:
            print(
                f"[{s.party_name}] label={s.stance_label} score={s.stance_score} "
                f"conf={s.confidence:.2f} evidence={s.evidence_url} rationale={s.rationale}"
            )
    else:
        print("No scores returned.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="税制")
    parser.add_argument("--keyword", default="税")
    args = parser.parse_args()
    run(topic=args.topic, keyword=args.keyword)
