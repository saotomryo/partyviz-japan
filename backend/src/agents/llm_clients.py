from __future__ import annotations

import json
from typing import List

import google.generativeai as genai
import httpx
from openai import OpenAI

from .prompting import load_prompt
from .json_parse import parse_json

from .base import LLMClient, PartyDocs, ScoreResult


SYSTEM_PROMPT = load_prompt("score_relative_openai.txt")


def build_payload(topic: str, party_docs: List[PartyDocs], *, max_docs_per_party: int = 3, max_chars: int = 4000) -> str:
    payload = {
        "topic": topic,
        "parties": [
            {
                "party_name": pd.party_name,
                "docs": [{"url": d.url, "content": d.content[:max_chars]} for d in pd.docs[:max_docs_per_party]],
            }
            for pd in party_docs
            if pd.docs
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


class OpenAILLMClient(LLMClient):
    """OpenAIベースのスコアリングクライアント（chat.completions）。"""

    def __init__(self, api_key: str, model: str = "gpt-5-mini", use_search: bool = False):
        # httpx は環境変数のプロキシ設定を自動参照する。接続に問題がある場合は環境変数を確認すること。
        http_client = httpx.Client(timeout=30, follow_redirects=True)
        self.client = OpenAI(api_key=api_key, http_client=http_client)
        self.model = model
        self.use_search = use_search  # 将来的にweb_search toolを有効化するフラグ

    def score_policies(self, *, topic: str, party_docs: List[PartyDocs]) -> List[ScoreResult]:
        user_content = build_payload(topic, party_docs)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"次のJSONを読み、各政党ごとにスコアを配列で返してください。必ずJSONのみを返す。\n{user_content}",
            },
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
        )
        text = response.choices[0].message.content or "[]"
        try:
            data = parse_json(text)
        except Exception:
            # モデルの応答がJSONでない場合は空を返す
            return []

        results: List[ScoreResult] = []
        for item in data:
            try:
                results.append(
                    ScoreResult(
                        party_name=item.get("party_name", ""),
                        stance_label=item.get("stance_label", "unknown"),
                        stance_score=int(item.get("stance_score", 0)),
                        confidence=float(item.get("confidence", 0.0)),
                        rationale=item.get("rationale", ""),
                        evidence_url=item.get("evidence_url"),
                    )
                )
            except Exception:
                continue
        return results


class GeminiLLMClient(LLMClient):
    """Google Geminiベースのスコアリングクライアント（生成AI検索を有効にする想定）。"""

    def __init__(self, api_key: str, model: str = "models/gemini-2.5-flash", use_search: bool = False):
        genai.configure(api_key=api_key)
        self.model = model
        self.use_search = use_search  # 将来的にgoogle_search groundingを使うフラグ

    def score_policies(self, *, topic: str, party_docs: List[PartyDocs]) -> List[ScoreResult]:
        model = genai.GenerativeModel(self.model)
        payload = build_payload(topic, party_docs)

        prompt = (
            f"{SYSTEM_PROMPT}\n"
            "次のJSONに含まれる各政党について、配列で結果を返してください。必ずJSONのみを返す。\n"
            f"{payload}"
        )

        resp = model.generate_content(prompt)
        text = resp.text or "[]"
        try:
            data = parse_json(text)
        except Exception:
            return []

        results: List[ScoreResult] = []
        for item in data:
            try:
                results.append(
                    ScoreResult(
                        party_name=item.get("party_name", ""),
                        stance_label=item.get("stance_label", "unknown"),
                        stance_score=int(item.get("stance_score", 0)),
                        confidence=float(item.get("confidence", 0.0)),
                        rationale=item.get("rationale", ""),
                        evidence_url=item.get("evidence_url"),
                    )
                )
            except Exception:
                continue
        return results
