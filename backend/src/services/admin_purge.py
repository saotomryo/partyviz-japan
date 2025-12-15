from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session


Target = Literal["parties", "topics", "events", "all"]


@dataclass(frozen=True)
class PurgeResult:
    deleted: dict[str, int]


def purge(db: Session, *, targets: Iterable[Target], dry_run: bool = False) -> PurgeResult:
    normalized = set(targets)
    if "all" in normalized:
        normalized = {"parties", "topics", "events"}

    statements: list[tuple[str, str]] = []

    # topics/topic_rubrics
    if "topics" in normalized:
        statements.extend(
            [
                ("topic_scores", "DELETE FROM topic_scores"),
                ("score_runs", "DELETE FROM score_runs"),
                ("topic_rubrics", "DELETE FROM topic_rubrics"),
                ("topics", "DELETE FROM topics"),
            ]
        )

    # party related
    if "parties" in normalized:
        statements.extend(
            [
                ("topic_scores", "DELETE FROM topic_scores"),
                ("score_runs", "DELETE FROM score_runs"),
                ("party_change_history", "DELETE FROM party_change_history"),
                ("party_registry", "DELETE FROM party_registry"),
            ]
        )

    # events/snapshots
    if "events" in normalized:
        statements.extend(
            [
                ("party_discovery_events", "DELETE FROM party_discovery_events"),
                ("source_snapshots", "DELETE FROM source_snapshots"),
            ]
        )

    deleted: dict[str, int] = {}
    if dry_run:
        for table, _ in statements:
            deleted[table] = 0
        return PurgeResult(deleted=deleted)

    for table, sql in statements:
        res = db.execute(text(sql))
        try:
            deleted[table] = int(res.rowcount or 0)
        except Exception:
            deleted[table] = 0

    db.commit()
    return PurgeResult(deleted=deleted)
