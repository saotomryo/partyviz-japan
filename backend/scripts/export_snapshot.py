from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy.orm import Session

# Ensure project root (backend/) is on sys.path so that `src` can be imported when running as a script
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.db import SessionLocal
from src.services import snapshot_export


def main() -> None:
    parser = argparse.ArgumentParser(description="Export PartyViz snapshot JSON for static hosting.")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[2] / "frontend" / "data" / "snapshot.json"),
        help="Output path (default: frontend/data/snapshot.json)",
    )
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    db: Session = SessionLocal()
    try:
        data = snapshot_export.build_snapshot(db)
    finally:
        db.close()

    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote snapshot: {out_path}")


if __name__ == "__main__":
    main()

