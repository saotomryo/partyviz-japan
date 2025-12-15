from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure project root (backend/) is on sys.path so that `src` can be imported when running as a script
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.db import SessionLocal
from src.services import party_registry_auto


def main() -> None:
    parser = argparse.ArgumentParser(description="政党レジストリをLLM検索で自動取得しDBへ反映する")
    parser.add_argument(
        "--query",
        default="日本の国政政党（国会に議席のある政党）と主要な新党・政治団体の公式サイト一覧 チームみらい",
    )
    parser.add_argument("--provider", default="auto", choices=["auto", "gemini", "openai"])
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        used_provider, results, summary = party_registry_auto.discover_and_upsert_parties(
            db,
            query=args.query,
            provider=args.provider,
            limit=args.limit,
            dry_run=args.dry_run,
            debug=False,
        )
    finally:
        db.close()

    print(json.dumps({"provider": used_provider, **summary, "results": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
