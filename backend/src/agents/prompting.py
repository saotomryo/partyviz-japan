from __future__ import annotations

from pathlib import Path


def default_prompt_dir() -> Path:
    # backend/src/agents/prompting.py -> parents[0]=agents, [1]=src, [2]=backend
    return Path(__file__).resolve().parents[2] / "prompts"


def load_prompt(name: str) -> str:
    path = default_prompt_dir() / name
    return path.read_text(encoding="utf-8")
