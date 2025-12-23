from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

# Ensure project root (backend/) is on sys.path so that `src` can be imported when running as a script
sys.path.append(str(Path(__file__).resolve().parents[1]))

from src.db import SessionLocal
from src.db import models


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def _as_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(str(value))


def _as_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _first_evidence_url(score_item: dict[str, Any]) -> str | None:
    evidence = score_item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return None
    first = evidence[0]
    if not isinstance(first, dict):
        return None
    url = first.get("url")
    if isinstance(url, str) and url.strip():
        return url.strip()
    return None


def _first_evidence_quote(score_item: dict[str, Any]) -> str | None:
    evidence = score_item.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return None
    first = evidence[0]
    if not isinstance(first, dict):
        return None
    quote = first.get("quote")
    if isinstance(quote, str) and quote.strip():
        return quote
    return None


def _axis_label_or_default(value: Any, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _upsert_topic(db: Session, topic: dict[str, Any]) -> None:
    topic_id = str(topic["topic_id"])
    row = db.get(models.Topic, topic_id)
    if not row:
        row = models.Topic(topic_id=topic_id)
        db.add(row)
    row.name = str(topic.get("name") or "")
    row.description = str(topic.get("description") or "")


def _upsert_party(db: Session, party_id: uuid.UUID, name_ja: str, official_home_url: str | None) -> None:
    row = db.get(models.PartyRegistry, party_id)
    if not row:
        row = models.PartyRegistry(party_id=party_id)
        db.add(row)
    row.name_ja = name_ja
    if official_home_url and (not row.official_home_url):
        row.official_home_url = official_home_url


def _ensure_rubric(db: Session, topic_id: str, payload: dict[str, Any], replace: bool) -> None:
    if replace:
        db.execute(update(models.TopicRubric).where(models.TopicRubric.topic_id == topic_id).values(status="archived"))

    existing = db.scalar(
        select(models.TopicRubric)
        .where(models.TopicRubric.topic_id == topic_id)
        .order_by(models.TopicRubric.version.desc())
        .limit(1)
    )
    if existing and not replace:
        return

    rubric_version = payload.get("rubric_version")
    version = int(rubric_version) if isinstance(rubric_version, int) and rubric_version > 0 else 1
    axis_a = _axis_label_or_default(payload.get("axis_a_label"), "反対")
    axis_b = _axis_label_or_default(payload.get("axis_b_label"), "賛成")

    db.add(
        models.TopicRubric(
            topic_id=topic_id,
            version=version,
            status="active",
            axis_a_label=axis_a,
            axis_b_label=axis_b,
            steps=[],
            generated_by="snapshot_import",
        )
    )


def _upsert_score_run(db: Session, topic_id: str, run: dict[str, Any], fallback_created_at: datetime | None) -> uuid.UUID:
    run_id_raw = run.get("run_id")
    run_id = _as_uuid(run_id_raw) if run_id_raw else uuid.uuid5(uuid.NAMESPACE_URL, f"snapshot:{topic_id}")

    row = db.get(models.ScoreRun, run_id)
    if not row:
        row = models.ScoreRun(run_id=run_id, topic_id=topic_id)
        db.add(row)

    row.topic_id = topic_id
    row.search_provider = run.get("search_provider")
    row.search_model = run.get("search_model")
    row.score_provider = run.get("score_provider")
    row.score_model = run.get("score_model")
    row.meta = run.get("meta") if isinstance(run.get("meta"), dict) else {}

    created_at = _parse_dt(run.get("created_at")) or fallback_created_at
    if created_at:
        row.created_at = created_at
    return run_id


def _replace_scores_for_run(
    db: Session, topic_id: str, run_id: uuid.UUID, scores: list[dict[str, Any]], fallback_created_at: datetime | None
) -> int:
    db.execute(delete(models.TopicScore).where(models.TopicScore.run_id == run_id))

    created_at = fallback_created_at or datetime.now()
    inserted = 0
    for item in scores:
        if not isinstance(item, dict):
            continue
        party_id_raw = item.get("entity_id")
        if not party_id_raw:
            continue
        party_id = _as_uuid(party_id_raw)

        evidence = item.get("evidence")
        evidence_json = evidence if isinstance(evidence, list) else []

        db.add(
            models.TopicScore(
                run_id=run_id,
                topic_id=topic_id,
                party_id=party_id,
                stance_label=str(item.get("stance_label") or ""),
                stance_score=int(item.get("stance_score") or 0),
                confidence=_as_decimal(item.get("confidence")),
                rationale=str(item.get("rationale") or ""),
                evidence_url=_first_evidence_url(item),
                evidence_quote=_first_evidence_quote(item),
                evidence=evidence_json,
                created_at=created_at,
            )
        )
        inserted += 1

    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Import PartyViz snapshot.json into PostgreSQL (topics/parties/scores).")
    parser.add_argument(
        "--in",
        dest="in_path",
        default=str(Path(__file__).resolve().parents[2] / "frontend" / "data" / "snapshot.json"),
        help="Input snapshot path (default: frontend/data/snapshot.json)",
    )
    parser.add_argument(
        "--replace-rubrics",
        action="store_true",
        help="Archive existing rubrics for the imported topics and create a new active rubric from snapshot axis labels.",
    )
    args = parser.parse_args()

    in_path = Path(args.in_path).resolve()
    data = json.loads(in_path.read_text(encoding="utf-8"))
    generated_at = _parse_dt(data.get("generated_at"))

    topics = data.get("topics")
    positions = data.get("positions")
    runs = data.get("runs") or {}

    if not isinstance(topics, list) or not isinstance(positions, dict):
        raise SystemExit("Invalid snapshot format: expected {topics: [...], positions: {...}}")

    db: Session = SessionLocal()
    try:
        seen_topic_ids: set[str] = set()
        for t in topics:
            if isinstance(t, dict) and t.get("topic_id"):
                topic_id = str(t["topic_id"])
                if topic_id in seen_topic_ids:
                    continue
                seen_topic_ids.add(topic_id)
                _upsert_topic(db, t)

        for topic_id, payload in positions.items():
            if not isinstance(payload, dict):
                continue
            embedded_topic = payload.get("topic")
            if isinstance(embedded_topic, dict) and embedded_topic.get("topic_id"):
                topic_id = str(embedded_topic["topic_id"])
                if topic_id in seen_topic_ids:
                    continue
                seen_topic_ids.add(topic_id)
                _upsert_topic(db, embedded_topic)

        db.flush()

        party_seen: dict[uuid.UUID, dict[str, Any]] = {}
        for topic_id, payload in positions.items():
            if not isinstance(payload, dict):
                continue
            scores = payload.get("scores")
            if not isinstance(scores, list):
                continue
            for item in scores:
                if not isinstance(item, dict):
                    continue
                if item.get("entity_type") != "party":
                    continue
                entity_id = item.get("entity_id")
                if not entity_id:
                    continue
                party_id = _as_uuid(entity_id)
                name_ja = str(item.get("entity_name") or "")
                official_home_url = _first_evidence_url(item)
                if party_id not in party_seen:
                    party_seen[party_id] = {"name_ja": name_ja, "official_home_url": official_home_url}
                else:
                    if official_home_url and not party_seen[party_id].get("official_home_url"):
                        party_seen[party_id]["official_home_url"] = official_home_url

        for party_id, info in party_seen.items():
            _upsert_party(db, party_id, str(info.get("name_ja") or ""), info.get("official_home_url"))

        for topic_id, payload in positions.items():
            if not isinstance(payload, dict):
                continue
            _ensure_rubric(db, str(topic_id), payload, replace=args.replace_rubrics)

            scores = payload.get("scores")
            if not isinstance(scores, list) or not scores:
                continue

            run_payload = runs.get(topic_id) if isinstance(runs, dict) else None
            run_payload = run_payload if isinstance(run_payload, dict) else {"topic_id": topic_id, "created_at": None}
            run_id = _upsert_score_run(db, str(topic_id), run_payload, fallback_created_at=generated_at)
            inserted = _replace_scores_for_run(
                db, str(topic_id), run_id, [s for s in scores if isinstance(s, dict)], fallback_created_at=generated_at
            )
            print(f"{topic_id}: imported {inserted} scores (run_id={run_id})")

        db.commit()
        print(f"Imported snapshot: {in_path}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
