from __future__ import annotations

import json
import re
from typing import Any


def _strip_code_fences(text: str) -> str:
    """
    LLMが ```json ... ``` のようなコードフェンス付きで返すことがあるため除去する。
    """
    s = text.strip()
    if s.startswith("```"):
        # 最初の ``` 行を落とす
        s = re.sub(r"^```[a-zA-Z0-9_-]*\n", "", s)
        # 末尾の ``` を落とす
        s = re.sub(r"\n```$", "", s.strip())
    return s.strip()


def parse_json(text: str) -> Any:
    """
    LLM出力からJSONをパースする。
    - 先頭/末尾のコードフェンスを除去
    - それでも失敗する場合は、最初の {/[ から最後の }/] までを抜き出して再試行
    """
    s = _strip_code_fences(text)
    try:
        return json.loads(s)
    except Exception:
        pass

    # JSON本体のみ抽出（最小限のヒューリスティック）
    start_candidates = [s.find("["), s.find("{")]
    start_candidates = [i for i in start_candidates if i != -1]
    if not start_candidates:
        raise
    start = min(start_candidates)
    end_candidates = [s.rfind("]"), s.rfind("}")]
    end_candidates = [i for i in end_candidates if i != -1]
    if not end_candidates:
        raise
    end = max(end_candidates) + 1
    return json.loads(s[start:end])

