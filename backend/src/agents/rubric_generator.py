from __future__ import annotations

import json
from dataclasses import dataclass

from openai import OpenAI
import google.generativeai as genai

from .json_parse import parse_json
from .prompting import load_prompt


@dataclass
class RubricDraft:
    topic_id: str
    name: str
    description: str | None
    axis_a_label: str
    axis_b_label: str
    steps: list[dict]
    llm_provider: str
    llm_model: str
    prompt_version: str


PROMPT_VERSION = "rubric_generate_v1"


def _build_user_payload(*, topic_name: str, description: str | None, axis_a_hint: str | None, axis_b_hint: str | None, steps_count: int) -> str:
    return json.dumps(
        {
            "topic_name": topic_name,
            "description": description,
            "axis_a_hint": axis_a_hint,
            "axis_b_hint": axis_b_hint,
            "steps_count": steps_count,
        },
        ensure_ascii=False,
    )


def generate_rubric_openai(*, api_key: str, model: str, topic_name: str, description: str | None, axis_a_hint: str | None, axis_b_hint: str | None, steps_count: int) -> RubricDraft:
    prompt = load_prompt("rubric_generate.txt")
    user = _build_user_payload(
        topic_name=topic_name,
        description=description,
        axis_a_hint=axis_a_hint,
        axis_b_hint=axis_b_hint,
        steps_count=steps_count,
    )
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user},
        ],
    )
    text = resp.choices[0].message.content or "{}"
    data = parse_json(text)
    return RubricDraft(
        topic_id=str(data.get("topic_id") or ""),
        name=str(data.get("name") or topic_name),
        description=data.get("description") or description,
        axis_a_label=str(data.get("axis_a_label") or axis_a_hint or "Axis A"),
        axis_b_label=str(data.get("axis_b_label") or axis_b_hint or "Axis B"),
        steps=list(data.get("steps") or []),
        llm_provider="openai",
        llm_model=model,
        prompt_version=PROMPT_VERSION,
    )


def generate_rubric_gemini(*, api_key: str, model: str, topic_name: str, description: str | None, axis_a_hint: str | None, axis_b_hint: str | None, steps_count: int) -> RubricDraft:
    prompt = load_prompt("rubric_generate.txt")
    user = _build_user_payload(
        topic_name=topic_name,
        description=description,
        axis_a_hint=axis_a_hint,
        axis_b_hint=axis_b_hint,
        steps_count=steps_count,
    )
    genai.configure(api_key=api_key)
    m = genai.GenerativeModel(model)
    resp = m.generate_content(f"{prompt}\n{user}")
    text = resp.text or "{}"
    data = parse_json(text)
    return RubricDraft(
        topic_id=str(data.get("topic_id") or ""),
        name=str(data.get("name") or topic_name),
        description=data.get("description") or description,
        axis_a_label=str(data.get("axis_a_label") or axis_a_hint or "Axis A"),
        axis_b_label=str(data.get("axis_b_label") or axis_b_hint or "Axis B"),
        steps=list(data.get("steps") or []),
        llm_provider="gemini",
        llm_model=model,
        prompt_version=PROMPT_VERSION,
    )

