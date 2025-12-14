from __future__ import annotations

import json
from typing import List

import google.generativeai as genai
import httpx
from openai import OpenAI

from .base import DiscoveryCandidate
from ..settings import settings

SYSTEM_PROMPT_SEARCH = """あなたは公的情報を優先するリサーチャーです。
日本の政党の公式サイトURLを推定し、政党名とURLをJSON配列で返してください。
- 公式サイトを優先してください。Wikipediaやまとめサイトは除外。
- レスポンスは JSON のみ (例: [{"name_ja":"政党X","url":"https://example.jp"}])
"""


class OpenAILLMSearchClient:
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        http_client = httpx.Client(timeout=30, follow_redirects=True)
        self.client = OpenAI(api_key=api_key, http_client=http_client)
        self.model = model

    def search_parties(self, query: str) -> List[DiscoveryCandidate]:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_SEARCH},
            {"role": "user", "content": f"クエリ: {query}\n政党名と公式URLを返してください。"},
        ]
        resp = self.client.chat.completions.create(model=self.model, messages=messages)
        text = resp.choices[0].message.content or "[]"
        try:
            data = json.loads(text)
        except Exception:
            return []
        results: List[DiscoveryCandidate] = []
        for item in data:
            url = item.get("url") or item.get("official_url")
            name = item.get("name_ja") or item.get("name") or item.get("party")
            if not url or not name:
                continue
            results.append(DiscoveryCandidate(name_ja=name, candidate_url=url, source="openai-llm-search"))
        return results


class GeminiLLMSearchClient:
    def __init__(self, api_key: str, model: str = "models/gemini-1.5-flash"):
        genai.configure(api_key=api_key)
        self.model = model

    def search_parties(self, query: str) -> List[DiscoveryCandidate]:
        model = genai.GenerativeModel(self.model)
        prompt = f"{SYSTEM_PROMPT_SEARCH}\nクエリ: {query}\n政党名と公式URLを返してください。"
        resp = model.generate_content(prompt)
        text = resp.text or "[]"
        try:
            data = json.loads(text)
        except Exception:
            return []
        results: List[DiscoveryCandidate] = []
        for item in data:
            url = item.get("url") or item.get("official_url")
            name = item.get("name_ja") or item.get("name") or item.get("party")
            if not url or not name:
                continue
            results.append(DiscoveryCandidate(name_ja=name, candidate_url=url, source="gemini-llm-search"))
        return results
