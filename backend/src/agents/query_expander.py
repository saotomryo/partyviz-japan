from __future__ import annotations

import json
from typing import List

import google.generativeai as genai
import httpx
from openai import OpenAI

from .json_parse import parse_json
from .prompting import load_prompt


SYSTEM_PROMPT = load_prompt("query_expand.txt")


def _sanitize(items: list) -> List[str]:
    out: list[str] = []
    seen: set[str] = set()
    for x in items or []:
        if not isinstance(x, str):
            continue
        t = " ".join(x.split()).strip()
        if not t:
            continue
        if t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out[:12]

def _coerce_list(data) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("subkeywords", "keywords", "items", "results"):
            v = data.get(key)
            if isinstance(v, list):
                return v
    return []


def generate_subkeywords_openai(*, api_key: str, model: str, topic: str) -> List[str]:
    client = OpenAI(api_key=api_key, http_client=httpx.Client(timeout=30, follow_redirects=True))
    for attempt in range(2):
        user = f"トピック: {topic}\nJSON配列のみで返してください。"
        if attempt == 1:
            user = (
                f"トピック: {topic}\n"
                "厳守: 返答は [\"...\"] 形式の JSON 配列（文字列配列）のみ。説明文・箇条書き・前置き禁止。\n"
                "例: [\"廃止\",\"増額\",\"財源\"]"
            )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ]
        resp = client.chat.completions.create(model=model, messages=messages)
        text = resp.choices[0].message.content or "[]"
        try:
            data = parse_json(text)
        except Exception:
            data = []
        kw = _sanitize(_coerce_list(data))
        if kw:
            return kw
    return []


def generate_subkeywords_gemini(*, api_key: str, model: str, topic: str) -> List[str]:
    genai.configure(api_key=api_key)
    m = genai.GenerativeModel(model)
    for attempt in range(2):
        prompt = f"{SYSTEM_PROMPT}\nトピック: {topic}\nJSON配列のみで返してください。"
        if attempt == 1:
            prompt = (
                f"{SYSTEM_PROMPT}\n"
                f"トピック: {topic}\n"
                "厳守: 返答は [\"...\"] 形式の JSON 配列（文字列配列）のみ。説明文・箇条書き・前置き禁止。\n"
                "例: [\"廃止\",\"増額\",\"財源\"]"
            )
        resp = m.generate_content(prompt)
        text = (resp.text or "").strip() or "[]"
        try:
            data = parse_json(text)
        except Exception:
            data = []
        kw = _sanitize(_coerce_list(data))
        if kw:
            return kw
    return []
