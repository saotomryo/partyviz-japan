from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy.orm import Session

# Ensure project root (backend/) is on sys.path so that `src` can be imported when running as a script
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.db import SessionLocal
from src.services import admin_purge
from src.services import db_backup


def main() -> None:
    parser = argparse.ArgumentParser(description="Import PartyViz DB backup JSON (tables restore).")
    parser.add_argument(
        "--in",
        dest="in_path",
        default=str(Path(__file__).resolve().parents[1] / "backups" / "backup.json"),
        help="Input path (default: backend/backups/backup.json)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Purge existing DB data (targets=all) before import.",
    )
    parser.add_argument(
        "--include-binary-snapshots",
        action="store_true",
        help="Allow restoring `source_snapshots.content` from base64 (if present).",
    )
    args = parser.parse_args()

    in_path = Path(args.in_path).resolve()
    payload = db_backup.loads(in_path.read_text(encoding="utf-8"))

    db: Session = SessionLocal()
    try:
        if args.replace:
            admin_purge.purge(db, targets=["all"], dry_run=False)
        inserted = db_backup.import_backup(db, payload=payload, allow_binary_snapshots=bool(args.include_binary_snapshots))
    finally:
        db.close()

    for k, v in inserted.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()

