from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID as PGUUID
from sqlalchemy.orm import Session
from sqlalchemy.types import LargeBinary, Numeric

from ..db import models


BACKUP_FORMAT_VERSION = 1


@dataclass(frozen=True)
class BackupPayload:
    version: int
    generated_at: str
    tables: dict[str, list[dict[str, Any]]]


EXPORT_TABLES: dict[str, type] = {
    "topics": models.Topic,
    "topic_rubrics": models.TopicRubric,
    "party_registry": models.PartyRegistry,
    "party_policy_sources": models.PartyPolicySource,
    "policy_documents": models.PolicyDocument,
    "policy_chunks": models.PolicyChunk,
    "party_discovery_events": models.PartyDiscoveryEvent,
    "source_snapshots": models.SourceSnapshot,
    "party_change_history": models.PartyChangeHistory,
    "score_runs": models.ScoreRun,
    "topic_scores": models.TopicScore,
}


IMPORT_ORDER: list[str] = [
    "topics",
    "party_registry",
    "party_policy_sources",
    "policy_documents",
    "policy_chunks",
    "topic_rubrics",
    "score_runs",
    "topic_scores",
    "party_discovery_events",
    "source_snapshots",
    "party_change_history",
]


def _dt_now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _jsonable(value: Any, *, include_binaries: bool) -> Any:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        if not include_binaries:
            return None
        return base64.b64encode(value).decode("ascii")
    if isinstance(value, (list, tuple)):
        return [_jsonable(v, include_binaries=include_binaries) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v, include_binaries=include_binaries) for k, v in value.items()}
    return value


def _iter_export_columns(model: type) -> list[sa.Column]:
    cols: list[sa.Column] = []
    for col in model.__table__.columns:  # type: ignore[attr-defined]
        if getattr(col, "computed", None) is not None:
            continue
        cols.append(col)
    return cols


def export_backup(
    db: Session,
    *,
    include_tables: Iterable[str] | None = None,
    include_binaries: bool = False,
) -> BackupPayload:
    table_names = list(include_tables) if include_tables is not None else list(EXPORT_TABLES.keys())
    unknown = [t for t in table_names if t not in EXPORT_TABLES]
    if unknown:
        raise ValueError(f"Unknown table(s): {', '.join(unknown)}")

    tables: dict[str, list[dict[str, Any]]] = {}
    for name in table_names:
        model = EXPORT_TABLES[name]
        cols = _iter_export_columns(model)
        rows = db.query(model).all()
        payload_rows: list[dict[str, Any]] = []
        for row in rows:
            rec: dict[str, Any] = {}
            for col in cols:
                rec[col.name] = _jsonable(getattr(row, col.name), include_binaries=include_binaries)
            payload_rows.append(rec)
        tables[name] = payload_rows

    return BackupPayload(version=BACKUP_FORMAT_VERSION, generated_at=_dt_now_iso(), tables=tables)


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


def _as_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(str(value))
    except Exception:
        return None


def _as_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _coerce_for_column(col: sa.Column, value: Any, *, allow_binary: bool) -> Any:
    if value is None:
        return None

    ctype = col.type
    if isinstance(ctype, PGUUID):
        u = _as_uuid(value)
        return u
    if isinstance(ctype, TIMESTAMP):
        return _parse_dt(str(value))
    if isinstance(ctype, Numeric):
        return _as_decimal(value)
    if isinstance(ctype, LargeBinary):
        if not allow_binary:
            return None
        if isinstance(value, str) and value:
            try:
                return base64.b64decode(value)
            except Exception:
                return None
        return None
    return value


def _parse_payload(data: Mapping[str, Any]) -> BackupPayload:
    version = int(data.get("version") or 0)
    if version != BACKUP_FORMAT_VERSION:
        raise ValueError(f"Unsupported backup version: {version}")
    generated_at = str(data.get("generated_at") or "")
    tables_raw = data.get("tables")
    if not isinstance(tables_raw, dict):
        raise ValueError("Invalid backup payload: tables must be an object")
    tables: dict[str, list[dict[str, Any]]] = {}
    for k, v in tables_raw.items():
        if not isinstance(k, str):
            continue
        if not isinstance(v, list):
            continue
        rows: list[dict[str, Any]] = [r for r in v if isinstance(r, dict)]
        tables[k] = rows
    return BackupPayload(version=version, generated_at=generated_at, tables=tables)


def dumps(payload: BackupPayload) -> str:
    return json.dumps(
        {"version": payload.version, "generated_at": payload.generated_at, "tables": payload.tables},
        ensure_ascii=False,
        indent=2,
    )


def loads(text: str) -> BackupPayload:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Invalid backup payload: root must be an object")
    return _parse_payload(data)


def import_backup(
    db: Session,
    *,
    payload: BackupPayload,
    allow_binary_snapshots: bool = False,
) -> dict[str, int]:
    inserted: dict[str, int] = {}
    for name in IMPORT_ORDER:
        rows = payload.tables.get(name) or []
        if not rows:
            inserted[name] = 0
            continue
        model = EXPORT_TABLES.get(name)
        if model is None:
            continue

        cols_by_name = {c.name: c for c in _iter_export_columns(model)}
        count = 0
        for rec in rows:
            if not isinstance(rec, dict):
                continue
            obj_kwargs: dict[str, Any] = {}
            for key, val in rec.items():
                col = cols_by_name.get(key)
                if col is None:
                    continue
                allow_binary = allow_binary_snapshots and (name == "source_snapshots")
                obj_kwargs[key] = _coerce_for_column(col, val, allow_binary=allow_binary)
            db.add(model(**obj_kwargs))
            count += 1
        db.flush()
        inserted[name] = count

    db.commit()
    return inserted

