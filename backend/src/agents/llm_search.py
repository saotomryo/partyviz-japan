from __future__ import annotations

import json
from typing import List
from urllib.parse import urlparse

import google.generativeai as genai
import httpx
from openai import OpenAI

from .base import DiscoveryCandidate, EvidenceSnippet, PolicyEvidence, ResolvedParty
from .json_parse import parse_json
from .prompting import load_prompt

SYSTEM_PROMPT_SEARCH = load_prompt("party_discovery_openai.txt")
SYSTEM_PROMPT_EVIDENCE = load_prompt("policy_evidence_bulk_openai.txt")


class OpenAILLMSearchClient:
    """
    OpenAIの検索対応モデル（例: gpt-4o-mini-search-preview）を用いて、
    党公式URLの推定と、公式ドメイン内の政策根拠URL抽出を行う。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini-search-preview",
        search_context_size: str = "high",
        debug: bool = False,
        timeout_sec: int = 120,
    ):
        self.http_client = httpx.Client(timeout=timeout_sec, follow_redirects=True)
        self.client = OpenAI(api_key=api_key, http_client=self.http_client)
        self.api_key = api_key
        self.model = model
        self.search_context_size = search_context_size
        self.debug = debug
        self.last_raw_text: str | None = None
        self.last_error: str | None = None
        self.last_discovery_query: str | None = None
        self.last_evidence_payload: dict | None = None
        self.last_used: str | None = None  # "responses" | "chat"
        self.last_grounding_urls: list[str] | None = None
        self.last_usage: dict | None = None

    @staticmethod
    def _extract_urls(obj) -> list[str]:
        urls: list[str] = []

        def walk(x):
            if isinstance(x, dict):
                for k, v in x.items():
                    lk = str(k).lower()
                    if lk in {"url", "uri", "link", "source_url", "source_uri"} and isinstance(v, str):
                        urls.append(v)
                    walk(v)
            elif isinstance(x, list):
                for it in x:
                    walk(it)

        walk(obj)
        out: list[str] = []
        seen: set[str] = set()
        for u in urls:
            u2 = (u or "").strip()
            if not u2 or u2 in seen:
                continue
            seen.add(u2)
            out.append(u2)
        return out

    @staticmethod
    def _normalize_http_url(url: str) -> str:
        u = (url or "").strip()
        if not u:
            return ""
        if u.startswith("//"):
            u = "https:" + u
        if not (u.startswith("http://") or u.startswith("https://")):
            return ""
        return u

    @staticmethod
    def _normalize_compare_url(url: str) -> str:
        u = OpenAILLMSearchClient._normalize_http_url(url)
        return u[:-1] if u.endswith("/") else u

    def _responses_web_search(self, *, system: str, user: str, allowed_domains: list[str] | None = None) -> str:
        """
        OpenAI Responses API をHTTPで直接叩いて web_search_preview を使う。
        SDKバージョン差異で chat.completions に web_search_options を渡せないケースの回避策。
        """
        url = "https://api.openai.com/v1/responses"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        # まずは現在のResponses APIで一般的な形を試す
        tool: dict = {"type": "web_search_preview"}
        if self.search_context_size:
            tool["search_context_size"] = self.search_context_size
        if allowed_domains:
            tool["filters"] = {"allowed_domains": list(dict.fromkeys([d for d in allowed_domains if d]))}

        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "tools": [tool],
            "tool_choice": "auto",
        }

        if self.debug:
            print("[openai.responses] request model=", self.model)
        r = self.http_client.post(url, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        self.last_grounding_urls = self._extract_urls(data)
        self.last_usage = data.get("usage") if isinstance(data, dict) else None

        # output_text があればそれを優先
        if isinstance(data, dict):
            text = data.get("output_text")
            if isinstance(text, str) and text.strip():
                self.last_raw_text = text
                return text

            # output配列からテキストを寄せ集める
            out = data.get("output")
            if isinstance(out, list):
                parts: list[str] = []
                for item in out:
                    if not isinstance(item, dict):
                        continue
                    content = item.get("content")
                    if isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and isinstance(c.get("text"), str):
                                parts.append(c["text"])
                if parts:
                    joined = "\n".join(parts)
                    self.last_raw_text = joined
                    return joined

        return ""

    def search_parties(self, query: str) -> List[DiscoveryCandidate]:
        self.last_discovery_query = query
        # 可能ならResponses API + web_search_previewを使う
        try:
            self.last_error = None
            self.last_used = "responses"
            text = self._responses_web_search(system=SYSTEM_PROMPT_SEARCH, user=f"クエリ: {query}") or "[]"
        except Exception as e:
            self.last_error = f"responses_web_search failed ({type(e).__name__}: {e}); fallback to chat.completions"
            self.last_used = "chat"
            self.last_grounding_urls = None
            # フォールバック: 通常のChat Completions（検索なし、URLハルシネーションの可能性あり）
            try:
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT_SEARCH},
                    {"role": "user", "content": f"クエリ: {query}"},
                ]
                resp = self.client.chat.completions.create(model=self.model, messages=messages)
                text = resp.choices[0].message.content or "[]"
                self.last_raw_text = text
            except Exception as e2:
                self.last_error = f"{self.last_error}; chat.completions failed ({type(e2).__name__}: {e2})"
                return []
        try:
            data = parse_json(text)
        except Exception:
            return []

        results: List[DiscoveryCandidate] = []
        for item in data:
            url = item.get("official_url") or item.get("url")
            name = item.get("name_ja") or item.get("party_name") or item.get("name")
            if not url or not name:
                continue
            results.append(DiscoveryCandidate(name_ja=name, candidate_url=url, source="openai-web-search"))
        return results

    def find_policy_evidence_bulk(
        self,
        *,
        topic: str,
        parties: List[ResolvedParty],
        max_per_party: int = 3,
        allowed_domains: list[str] | None = None,
    ) -> List[PolicyEvidence]:
        party_payload = [
            {"party_name": p.name_ja, "official_url": p.official_url, "domain": urlparse(p.official_url).netloc}
            for p in parties
        ]
        self.last_evidence_payload = {"topic": topic, "parties": party_payload, "max_per_party": max_per_party}
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_EVIDENCE},
            {
                "role": "user",
                "content": json.dumps(
                    {"topic": topic, "parties": party_payload, "max_per_party": max_per_party},
                    ensure_ascii=False,
                ),
            },
        ]
        effective_allowed_domains: list[str] | None = allowed_domains
        if effective_allowed_domains is None:
            effective_allowed_domains = []
            for p in parties:
                host = urlparse(p.official_url).netloc
                if host:
                    effective_allowed_domains.append(host)
                effective_allowed_domains.extend(list(p.allowed_domains or []))

        try:
            self.last_error = None
            self.last_used = "responses"
            text = (
                self._responses_web_search(
                    system=SYSTEM_PROMPT_EVIDENCE,
                    user=messages[1]["content"],
                    allowed_domains=effective_allowed_domains,
                )
                or "[]"
            )
        except Exception as e:
            self.last_error = f"responses_web_search failed ({type(e).__name__}: {e}); fallback to chat.completions"
            self.last_used = "chat"
            self.last_grounding_urls = None
            self.last_usage = None
            try:
                resp = self.client.chat.completions.create(model=self.model, messages=messages)
                text = resp.choices[0].message.content or "[]"
                self.last_raw_text = text
            except Exception as e2:
                self.last_error = f"{self.last_error}; chat.completions failed ({type(e2).__name__}: {e2})"
                return []

        # 検索なし（chatフォールバック）の結果はURLハルシネーションになりやすいので採用しない
        if self.last_used != "responses":
            return []
        try:
            data = parse_json(text)
        except Exception:
            return []

        results: List[PolicyEvidence] = []
        grounded_set = {self._normalize_compare_url(u) for u in (self.last_grounding_urls or []) if u}
        for item in data:
            party_name = item.get("party_name") or ""
            evidence_items = []
            for ev in item.get("evidence", []) or []:
                url = ev.get("evidence_url") or ev.get("url")
                quote = ev.get("quote") or ""
                url = self._normalize_http_url(url or "")
                if not url:
                    continue
                # 検索ツールを使っている場合、groundingに含まれないURLはハルシネーションの可能性が高いので除外
                if self.last_used == "responses" and grounded_set and self._normalize_compare_url(url) not in grounded_set:
                    continue
                evidence_items.append(EvidenceSnippet(evidence_url=url, quote=quote))
            results.append(PolicyEvidence(party_name=party_name, evidence=evidence_items))
        return results


class GeminiLLMSearchClient:
    """
    Gemini Developer API の Grounding with Google Search を使う検索クライアント。

    現在の `google-generativeai` SDK(v0.8.x) だと `google_search_retrieval` を使う実装になるが、
    実API側が `google_search` ツールを要求するケースがあるため、HTTPで直接 `google_search` tool を呼ぶ。
    """

    def __init__(self, api_key: str, model: str = "models/gemini-1.5-flash", debug: bool = False):
        self.api_key = api_key
        self.model = model if model.startswith("models/") else f"models/{model}"
        self.debug = debug
        self.last_raw_text: str | None = None
        self.last_discovery_query: str | None = None
        self.last_evidence_payload: dict | None = None
        self.last_error: str | None = None
        self.last_grounding_urls: list[str] | None = None
        self.http_client = httpx.Client(timeout=120, follow_redirects=True)

    def _generate_grounded(self, prompt: str) -> str:
        """
        Grounding with Google Search: tools=[{"google_search":{}}]
        """
        url = f"https://generativelanguage.googleapis.com/v1beta/{self.model}:generateContent"
        params = {"key": self.api_key}
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"google_search": {}}],
        }
        r = self.http_client.post(url, params=params, json=payload)
        r.raise_for_status()
        data = r.json()
        self.last_grounding_urls = OpenAILLMSearchClient._extract_urls(data)
        # candidates[0].content.parts[].text を連結
        candidates = data.get("candidates") if isinstance(data, dict) else None
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        texts = [p.get("text", "") for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)]
        return "\n".join([t for t in texts if t]).strip()

    def _generate_plain(self, prompt: str) -> str:
        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model)
        resp = model.generate_content(prompt)
        return (resp.text or "").strip()

    def search_parties(self, query: str) -> List[DiscoveryCandidate]:
        self.last_discovery_query = query
        prompt = f"{SYSTEM_PROMPT_SEARCH}\nクエリ: {query}"
        try:
            self.last_error = None
            text = self._generate_grounded(prompt) or "[]"
        except Exception as e:
            self.last_error = f"grounded generateContent failed ({type(e).__name__}: {e}); fallback to plain"
            self.last_grounding_urls = None
            text = self._generate_plain(prompt) or "[]"
        self.last_raw_text = text
        if self.debug:
            print("[gemini.search] raw:", text[:400])
        try:
            data = parse_json(text)
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

    def find_policy_evidence_bulk(
        self,
        *,
        topic: str,
        parties: List[ResolvedParty],
        max_per_party: int = 3,
        allowed_domains: list[str] | None = None,
    ) -> List[PolicyEvidence]:
        party_payload = [
            {"party_name": p.name_ja, "official_url": p.official_url, "domain": urlparse(p.official_url).netloc}
            for p in parties
        ]
        self.last_evidence_payload = {"topic": topic, "parties": party_payload, "max_per_party": max_per_party}
        prompt = (
            f"{SYSTEM_PROMPT_EVIDENCE}\n"
            + json.dumps({"topic": topic, "parties": party_payload, "max_per_party": max_per_party}, ensure_ascii=False)
        )
        try:
            self.last_error = None
            text = self._generate_grounded(prompt) or "[]"
        except Exception as e:
            self.last_error = f"grounded generateContent failed ({type(e).__name__}: {e}); fallback to plain"
            self.last_grounding_urls = None
            # grounding無しの出力はURLハルシネーションになりやすいので採用しない
            return []
        self.last_raw_text = text
        if self.debug:
            print("[gemini.evidence] raw:", text[:400])
        try:
            data = parse_json(text)
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        results: List[PolicyEvidence] = []
        grounded_set = {OpenAILLMSearchClient._normalize_compare_url(u) for u in (self.last_grounding_urls or []) if u}
        for item in data:
            if not isinstance(item, dict):
                continue
            party_name = item.get("party_name") or ""
            evidence_items = []
            for ev in item.get("evidence", []) or []:
                if not isinstance(ev, dict):
                    continue
                url = ev.get("evidence_url") or ev.get("url")
                quote = ev.get("quote") or ""
                url = OpenAILLMSearchClient._normalize_http_url(url or "")
                if not url:
                    continue
                if grounded_set and OpenAILLMSearchClient._normalize_compare_url(url) not in grounded_set:
                    continue
                evidence_items.append(EvidenceSnippet(evidence_url=url, quote=quote))
            results.append(PolicyEvidence(party_name=party_name, evidence=evidence_items))
        return results
