from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def dprint(enabled: bool, *parts: object) -> None:
    if not enabled:
        return
    print(*parts)


def ensure_run_dir(base_dir: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base_dir / ts
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_text(enabled: bool, path: Path, text: str) -> None:
    if not enabled:
        return
    path.write_text(text, encoding="utf-8")


def save_json(enabled: bool, path: Path, data: Any) -> None:
    if not enabled:
        return
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
