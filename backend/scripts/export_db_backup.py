from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.orm import Session

# Ensure project root (backend/) is on sys.path so that `src` can be imported when running as a script
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.db import SessionLocal
from src.services import db_backup


def main() -> None:
    parser = argparse.ArgumentParser(description="Export PartyViz DB backup JSON (tables dump).")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[1] / "backups" / "backup.json"),
        help="Output path (default: backend/backups/backup.json)",
    )
    parser.add_argument(
        "--tables",
        default="",
        help="Comma-separated table names to include (default: all).",
    )
    parser.add_argument(
        "--include-binary-snapshots",
        action="store_true",
        help="Include `source_snapshots.content` as base64 (can be large).",
    )
    args = parser.parse_args()

    out_path = Path(args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tables = None
    if args.tables.strip():
        tables = [t.strip() for t in args.tables.split(",") if t.strip()]

    db: Session = SessionLocal()
    try:
        payload = db_backup.export_backup(
            db,
            include_tables=tables,
            include_binaries=bool(args.include_binary_snapshots),
        )
    finally:
        db.close()

    out_path.write_text(db_backup.dumps(payload), encoding="utf-8")
    print(f"Wrote DB backup: {out_path}")


if __name__ == "__main__":
    main()

