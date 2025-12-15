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
from urllib.parse import urlparse

# Ensure project root (backend/) is on sys.path so that `src` can be imported when running as a script
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.agents.base import DiscoveryCandidate, PartyDocs, PolicyDocument, ScoreResult
from src.agents.discovery import DiscoveryAgent
from src.agents.fetchers import HttpxFetcher
from src.agents.llm_clients import GeminiLLMClient, OpenAILLMClient
from src.agents.llm_search import GeminiLLMSearchClient, OpenAILLMSearchClient
from src.agents.resolution import ResolutionAgent
from src.agents.scorer import ScoringAgent
from src.agents.text_extract import html_to_text
from src.agents.debug import dprint, ensure_run_dir, save_json, save_text
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


def run(topic: str, keyword: str, *, party_limit: int, max_evidence_per_party: int):
    # 切り替え: USE_DUMMY_AGENTS=true ならダミー、false なら実処理（LLM検索＋HTTPフェッチ）
    use_dummy = settings.use_dummy_agents

    debug = settings.agent_debug
    save_runs = settings.agent_save_runs
    run_dir = None
    if save_runs:
        run_dir = ensure_run_dir(Path(__file__).resolve().parents[1] / "runs")
        dprint(debug, "run_dir=", str(run_dir))

    if use_dummy:
        print("ダミーエージェントを使用します。")
        discovery = DiscoveryAgent(DummySearchClient())
        fetcher = DummyFetcher()
    else:
        print("実エージェントを使用します。OPENAI_API_KEY または GEMINI_API_KEY が必要です。")
        search_provider = (settings.agent_search_provider or "auto").lower()
        if search_provider not in {"auto", "gemini", "openai"}:
            raise RuntimeError("AGENT_SEARCH_PROVIDER は auto|gemini|openai のいずれかにしてください")

        # デフォルトは Gemini を優先（grounding/searchの無料枠前提）
        if search_provider in {"auto", "gemini"} and settings.gemini_api_key:
            search_client = GeminiLLMSearchClient(
                api_key=settings.gemini_api_key,
                model=settings.gemini_search_model,
                debug=debug,
            )
            search_client_name = "GeminiLLMSearchClient"
        elif search_provider in {"auto", "openai"} and settings.openai_api_key:
            search_client = OpenAILLMSearchClient(
                api_key=settings.openai_api_key,
                model=settings.openai_search_model,
                debug=debug,
            )
            search_client_name = "OpenAILLMSearchClient"
        else:
            raise RuntimeError("検索用に GEMINI_API_KEY または OPENAI_API_KEY を設定してください（または AGENT_SEARCH_PROVIDER を見直してください）")

        print("検索クライアント:", search_client_name)
        if search_client_name == "OpenAILLMSearchClient":
            print("OpenAI検索: Responses API + web_search_preview を優先（失敗時は検索なしにフォールバック）")
        if search_client_name == "GeminiLLMSearchClient":
            print("Gemini検索: Developer API の google_search tool を使用（失敗時は検索なしにフォールバック）")
        discovery = DiscoveryAgent(search_client)
        print("HTTPクライアント: httpx")
        fetcher = HttpxFetcher()

    resolution = ResolutionAgent(fetcher)

    if use_dummy:
        llm_client = DummyLLM()
    else:
        score_provider = (settings.agent_score_provider or "auto").lower()
        if score_provider not in {"auto", "gemini", "openai"}:
            raise RuntimeError("AGENT_SCORE_PROVIDER は auto|gemini|openai のいずれかにしてください")

        # デフォルト: OpenAI (スコア精度優先) → Quota等で失敗したらGeminiに切替できるようにする
        if score_provider in {"auto", "openai"} and settings.openai_api_key:
            llm_client = OpenAILLMClient(api_key=settings.openai_api_key, model=settings.openai_score_model)
            score_client_name = "OpenAILLMClient"
        elif score_provider in {"auto", "gemini"} and settings.gemini_api_key:
            llm_client = GeminiLLMClient(api_key=settings.gemini_api_key, model=settings.gemini_score_model)
            score_client_name = "GeminiLLMClient"
        else:
            raise RuntimeError("スコア用に GEMINI_API_KEY または OPENAI_API_KEY を設定してください（または AGENT_SCORE_PROVIDER を見直してください）")

        dprint(debug, "score_client=", score_client_name)
    scorer = ScoringAgent(llm_client)

    discovery_query = "日本の政党 公式サイト 一覧"
    dprint(debug, "discovery_query=", discovery_query)
    candidates = discovery.run(query=discovery_query)
    dprint(debug, "candidates count=", len(candidates))
    if debug:
        pprint(candidates[:10])
    if run_dir:
        save_json(True, run_dir / "candidates.json", [c.__dict__ for c in candidates])
    parties = resolution.resolve_many(candidates)
    if party_limit <= 0:
        party_limit = int(getattr(settings, "party_limit", 0) or 0)
    if max_evidence_per_party <= 0:
        max_evidence_per_party = int(getattr(settings, "max_evidence_per_party", 0) or 0)
    if party_limit > 0:
        parties = parties[:party_limit]
    keywords = [keyword]

    print(f"Topic: {topic}, keywords: {keywords}")
    if debug and not use_dummy:
        if hasattr(search_client, "last_discovery_query"):
            print("discovery_query(sent):", getattr(search_client, "last_discovery_query"))
    dprint(debug, "=== Discovery results ===")
    dprint(debug, "resolved parties count=", len(parties))
    if debug:
        if parties:
            pprint(parties)
        else:
            print("No parties found.")
            if hasattr(search_client, "last_error") and getattr(search_client, "last_error"):
                print("search_client.last_error:", getattr(search_client, "last_error"))
            if hasattr(search_client, "last_raw_text") and getattr(search_client, "last_raw_text"):
                raw = getattr(search_client, "last_raw_text")
                print("search_client.last_raw_text (first 800 chars):")
                print(raw[:800])
                if run_dir:
                    save_text(True, run_dir / "search_raw.txt", raw)
            if hasattr(search_client, "last_discovery_query") and getattr(search_client, "last_discovery_query"):
                print("search_client.last_discovery_query:", getattr(search_client, "last_discovery_query"))

    dprint(debug, "=== Evidence search results ===")
    party_docs = []
    if use_dummy:
        # ダミー時は従来どおりトップページのみ
        for p in parties:
            try:
                html = fetcher.fetch(p.official_url)
            except Exception:
                continue
            party_docs.append(PartyDocs(party_name=p.name_ja, docs=[PolicyDocument(url=p.official_url, content=html[:8000])]))
    else:
        evidence_list = []
        if hasattr(search_client, "find_policy_evidence_bulk"):
            try:
                evidence_list = search_client.find_policy_evidence_bulk(
                    topic=topic,
                    parties=parties,
                    max_per_party=max_evidence_per_party,
                )
            except Exception as e:
                print("evidence search failed:", type(e).__name__, str(e))
                if hasattr(search_client, "last_error") and getattr(search_client, "last_error"):
                    print("search_client.last_error:", getattr(search_client, "last_error"))
                if hasattr(search_client, "last_raw_text") and getattr(search_client, "last_raw_text"):
                    raw = getattr(search_client, "last_raw_text")
                    print("search_client.last_raw_text (first 800 chars):")
                    print(raw[:800])
                if hasattr(search_client, "last_evidence_payload") and getattr(search_client, "last_evidence_payload"):
                    payload = getattr(search_client, "last_evidence_payload")
                    print("search_client.last_evidence_payload:")
                    pprint(payload)
                evidence_list = []
        by_party = {e.party_name: e for e in evidence_list}
        for p in parties:
            ev = by_party.get(p.name_ja)
            if not ev or not ev.evidence:
                dprint(debug, f"{p.name_ja}: evidence not found")
                continue
            official_domain = urlparse(p.official_url).netloc.lower()
            dprint(debug, f"{p.name_ja}: {len(ev.evidence)} evidence urls")
            docs = []
            for snip in ev.evidence:
                ev_domain = urlparse(snip.evidence_url).netloc.lower()
                if official_domain and not ev_domain.endswith(official_domain):
                    dprint(debug, f"  - SKIP (domain mismatch) {snip.evidence_url}")
                    continue
                dprint(debug, f"  - {snip.evidence_url} quote={snip.quote[:80]!r}")
                try:
                    html = fetcher.fetch(snip.evidence_url)
                except Exception:
                    dprint(debug, f"  - fetch failed: {snip.evidence_url}")
                    continue
                text = html_to_text(html)[:8000]
                docs.append(PolicyDocument(url=snip.evidence_url, content=text))
            if docs:
                party_docs.append(PartyDocs(party_name=p.name_ja, docs=docs))
    if party_docs:
        dprint(debug, "documents collected:")
        if debug:
            for pd in party_docs:
                print(f"{pd.party_name}: {len(pd.docs)} docs")
                for d in pd.docs:
                    print(f"  - {d.url} (len={len(d.content)})")
    else:
        dprint(debug, "No documents collected.")

    print("=== Scoring results ===")
    try:
        scores = scorer.score(topic=topic, party_docs=party_docs)
    except Exception as e:
        # OpenAIのinsufficient_quotaなどで落ちる場合、Geminiへ自動フォールバック（利用可能な場合）
        if (not use_dummy) and settings.gemini_api_key and (settings.agent_score_provider or "auto").lower() == "auto":
            print("score failed; fallback to Gemini:", type(e).__name__, str(e))
            scorer = ScoringAgent(GeminiLLMClient(api_key=settings.gemini_api_key, model=settings.gemini_score_model))
            scores = scorer.score(topic=topic, party_docs=party_docs)
        else:
            raise
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
    parser.add_argument("--party-limit", type=int, default=6, help="処理する政党数の上限（タイムアウト回避）")
    parser.add_argument("--max-evidence-per-party", type=int, default=2, help="各党の根拠URL上限")
    args = parser.parse_args()
    run(
        topic=args.topic,
        keyword=args.keyword,
        party_limit=args.party_limit,
        max_evidence_per_party=args.max_evidence_per_party,
    )
