from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models


@dataclass
class ImportStats:
    parties: int = 0
    items_total: int = 0
    documents_upserted: int = 0
    documents_unchanged: int = 0
    chunks_written: int = 0
    skipped: int = 0


def _hash_text(text: str) -> str:
    h = hashlib.sha256()
    h.update((text or "").encode("utf-8"))
    return h.hexdigest()


def _chunk_text(text: str, *, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    t = " ".join((text or "").split())
    if not t:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(t):
        end = min(len(t), start + chunk_size)
        chunks.append(t[start:end])
        if end == len(t):
            break
        start = max(0, end - overlap)
    return chunks


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    v = str(value).strip()
    if not v:
        return None
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(v)
    except ValueError:
        return None


def _as_uuid(value: Any) -> uuid.UUID | None:
    if not value:
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


def _clean_url(value: Any) -> str:
    u = str(value or "").strip()
    if not u:
        return ""
    return u.strip().strip("'\"")


def _normalize_text(value: Any) -> str:
    t = str(value or "")
    t = re.sub(r"\s+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def _content_text_for_item(item: dict[str, Any]) -> str:
    claim = _normalize_text(item.get("claim"))
    quote = _normalize_text(item.get("quote"))
    ctx = _normalize_text(item.get("quote_context"))
    citations = item.get("citations")
    citations_text = ""
    if isinstance(citations, list):
        parts = [str(c).strip() for c in citations if str(c).strip()]
        if parts:
            citations_text = "\n".join(parts)
    parts = []
    if claim:
        parts.append(f"CLAIM:\n{claim}")
    if quote:
        parts.append(f"QUOTE:\n{quote}")
    if ctx:
        parts.append(f"CONTEXT:\n{ctx}")
    if citations_text:
        parts.append(f"CITATIONS:\n{citations_text}")
    return "\n\n".join(parts).strip()


def _find_party_by_name(db: Session, name_ja: str) -> models.PartyRegistry | None:
    name = " ".join((name_ja or "").split())
    if not name:
        return None
    # canonical_key is computed from name_ja with whitespace removed and lowercased
    canonical = re.sub(r"\s+", "", name).lower()
    return db.scalar(select(models.PartyRegistry).where(models.PartyRegistry.canonical_key == canonical))


def _upsert_document(
    db: Session,
    *,
    party_id: uuid.UUID,
    url: str,
    doc_type: str,
    title: str | None,
    content_text: str,
    fetched_at: datetime | None,
) -> tuple[models.PolicyDocument, bool]:
    content_hash = _hash_text(content_text)
    doc = db.scalar(select(models.PolicyDocument).where(models.PolicyDocument.url == url))
    if doc and doc.hash == content_hash:
        return doc, False
    if not doc:
        doc = models.PolicyDocument(party_id=party_id, url=url, doc_type=doc_type)
        db.add(doc)
    doc.party_id = party_id
    doc.doc_type = doc_type
    doc.title = title
    doc.content_text = content_text
    doc.hash = content_hash
    if fetched_at:
        doc.fetched_at = fetched_at
    db.flush()
    return doc, True


def _replace_chunks(db: Session, *, doc: models.PolicyDocument, party_id: uuid.UUID, chunks: list[str], meta: dict[str, Any]) -> int:
    db.query(models.PolicyChunk).filter(models.PolicyChunk.doc_id == doc.doc_id).delete()
    written = 0
    for idx, text in enumerate(chunks):
        db.add(
            models.PolicyChunk(
                doc_id=doc.doc_id,
                party_id=party_id,
                chunk_index=idx,
                content=text,
                embedding=None,
                meta=meta,
            )
        )
        written += 1
    return written


def import_research_pack(db: Session, pack: dict[str, Any]) -> tuple[ImportStats, list[dict[str, Any]]]:
    if not isinstance(pack, dict):
        raise ValueError("pack must be an object")

    normalized = _normalize_to_partyviz_pack(pack)
    generator = str(normalized.get("generator") or "manual")
    parties = normalized.get("parties")
    if not isinstance(parties, list) or not parties:
        raise ValueError("parties must be a non-empty array")

    errors: list[dict[str, Any]] = []
    stats = ImportStats()

    # Group by (party_id, source_url) so multiple quotes/items per URL are preserved.
    grouped: dict[uuid.UUID, dict[str, dict[str, Any]]] = {}

    for p in parties:
        if not isinstance(p, dict):
            continue
        stats.parties += 1
        party_id = _as_uuid(p.get("party_id"))
        party_name_ja = str(p.get("party_name_ja") or "").strip()
        if not party_id:
            row = _find_party_by_name(db, party_name_ja)
            party_id = row.party_id if row else None
        if not party_id:
            errors.append({"scope": "party", "party_name_ja": party_name_ja, "reason": "party_not_found"})
            continue

        items = p.get("items")
        if not isinstance(items, list) or not items:
            continue

        by_url = grouped.setdefault(party_id, {})
        for item in items:
            if not isinstance(item, dict):
                continue
            stats.items_total += 1
            url = _clean_url(item.get("source_url"))
            if not url:
                stats.skipped += 1
                errors.append({"scope": "item", "party_id": str(party_id), "reason": "missing_source_url"})
                continue

            title = str(item.get("source_title") or "").strip() or None
            fetched_at = _parse_dt(item.get("fetched_at")) or datetime.now().astimezone()
            deprecated = bool(item.get("deprecated") is True)
            topic_ids = item.get("topic_ids")
            topic_ids_norm = [str(t).strip() for t in topic_ids] if isinstance(topic_ids, list) else []
            topic_ids_norm = [t for t in topic_ids_norm if t]

            content_text = _content_text_for_item(item)
            if not content_text:
                stats.skipped += 1
                errors.append({"scope": "item", "party_id": str(party_id), "source_url": url, "reason": "empty_content"})
                continue

            entry = by_url.setdefault(
                url,
                {
                    "title": title,
                    "fetched_at": fetched_at,
                    "items": [],
                },
            )
            # keep the most informative title (prefer existing non-empty)
            if (not entry.get("title")) and title:
                entry["title"] = title
            # keep latest fetched_at
            if fetched_at and isinstance(entry.get("fetched_at"), datetime) and fetched_at > entry["fetched_at"]:
                entry["fetched_at"] = fetched_at
            entry["items"].append(
                {
                    "url": url,
                    "title": title,
                    "fetched_at": fetched_at,
                    "content_text": content_text,
                    "topic_ids": topic_ids_norm,
                    "deprecated": deprecated,
                    "deprecated_reason": str(item.get("deprecated_reason") or "").strip() or None,
                    "reliability": _as_decimal(item.get("reliability")),
                    "source_type": str(item.get("source_type") or "").strip() or None,
                    "raw": item,
                }
            )

    for party_id, by_url in grouped.items():
        for url, entry in by_url.items():
            items = entry.get("items") or []
            if not isinstance(items, list) or not items:
                continue

            # Combine for doc hash/content; chunks are stored per item with per-chunk meta.
            doc_parts: list[str] = []
            all_topic_ids: set[str] = set()
            for it in items:
                if not isinstance(it, dict):
                    continue
                topic_ids_norm = it.get("topic_ids") or []
                if isinstance(topic_ids_norm, list):
                    for t in topic_ids_norm:
                        if isinstance(t, str) and t.strip():
                            all_topic_ids.add(t.strip())
                header = ""
                if all_topic_ids:
                    # header only for readability; chunk meta is authoritative
                    pass
                doc_parts.append(it.get("content_text") or "")
            doc_content = "\n\n---\n\n".join([p for p in doc_parts if isinstance(p, str) and p.strip()]).strip()
            if not doc_content:
                stats.skipped += 1
                errors.append({"scope": "document", "party_id": str(party_id), "source_url": url, "reason": "empty_doc"})
                continue

            doc_type = "deep_research"
            doc, changed = _upsert_document(
                db,
                party_id=party_id,
                url=url,
                doc_type=doc_type,
                title=entry.get("title"),
                content_text=doc_content,
                fetched_at=entry.get("fetched_at"),
            )
            if changed:
                stats.documents_upserted += 1
            else:
                stats.documents_unchanged += 1

            # Replace chunks with item-level meta (so deprecated can be filtered per chunk).
            db.query(models.PolicyChunk).filter(models.PolicyChunk.doc_id == doc.doc_id).delete()
            chunk_index = 0
            for it in items:
                if not isinstance(it, dict):
                    continue
                base_meta: dict[str, Any] = {
                    "source_url": url,
                    "title": entry.get("title"),
                    "generator": generator,
                    "topic_ids": it.get("topic_ids") or [],
                    "deprecated": bool(it.get("deprecated") is True),
                    "deprecated_reason": it.get("deprecated_reason"),
                    "reliability": it.get("reliability"),
                    "source_type": it.get("source_type"),
                }
                base_meta = {k: v for k, v in base_meta.items() if v is not None and v != ""}
                chunks = _chunk_text(str(it.get("content_text") or ""))
                for c in chunks:
                    db.add(
                        models.PolicyChunk(
                            doc_id=doc.doc_id,
                            party_id=party_id,
                            chunk_index=chunk_index,
                            content=c,
                            embedding=None,
                            meta=base_meta,
                        )
                    )
                    chunk_index += 1
                    stats.chunks_written += 1

    db.commit()
    return stats, errors


def _normalize_to_partyviz_pack(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept multiple Deep Research output formats and normalize to partyviz_research_pack v1 shape.

    Supported:
    - partyviz_research_pack (v1)
    - craj_*_policy_research_pack (schema-based report)
    """
    fmt = str(payload.get("format") or "")
    if fmt == "partyviz_research_pack":
        version = int(payload.get("version") or 0)
        if version != 1:
            raise ValueError("unsupported version")
        return payload

    # Schema-based report format
    schema = payload.get("schema")
    if isinstance(schema, dict):
        name = str(schema.get("name") or "")
        version = str(schema.get("version") or "")
        if name.endswith("_policy_research_pack") and version.startswith("1"):
            party = schema.get("party") if isinstance(schema.get("party"), dict) else {}
            party_id = (party or {}).get("party_id")
            party_name_ja = (party or {}).get("name_ja")
            generator = "manual"
            topics = payload.get("topics")
            sources = payload.get("sources")
            sources_by_id: dict[str, dict[str, Any]] = {}
            if isinstance(sources, list):
                for s in sources:
                    if not isinstance(s, dict):
                        continue
                    sid = str(s.get("source_id") or "").strip()
                    if not sid:
                        continue
                    sources_by_id[sid] = s

            items: list[dict[str, Any]] = []
            if isinstance(topics, list):
                for t in topics:
                    if not isinstance(t, dict):
                        continue
                    topic_id = str(t.get("topic_id") or "").strip()
                    quotes = t.get("quotes")
                    if not isinstance(quotes, list):
                        continue
                    for q in quotes:
                        if not isinstance(q, dict):
                            continue
                        src = q.get("source") if isinstance(q.get("source"), dict) else {}
                        src_url = _clean_url((src or {}).get("url"))
                        if not src_url:
                            continue
                        src_id = str((src or {}).get("source_id") or "").strip()
                        src_meta = sources_by_id.get(src_id) or {}
                        items.append(
                            {
                                "source_url": src_url,
                                "source_title": str(src_meta.get("title_ja") or src_meta.get("title") or "").strip() or None,
                                "fetched_at": q.get("fetched_at") or src_meta.get("fetched_at") or schema.get("generated_at"),
                                "source_type": str(src_meta.get("source_type") or (src or {}).get("source_type") or "").strip()
                                or None,
                                "topic_ids": [topic_id] if topic_id else [],
                                "quote": q.get("quote_text_ja") or q.get("quote") or "",
                                "claim": q.get("claim_ja") or q.get("claim") or "",
                                "quote_context": "",
                                "deprecated": bool(q.get("deprecated") is True),
                                "deprecated_reason": q.get("deprecation_reason") or q.get("deprecated_reason") or None,
                            }
                        )

            return {
                "format": "partyviz_research_pack",
                "version": 1,
                "generated_at": schema.get("generated_at"),
                "generator": generator,
                "parties": [
                    {
                        "party_id": party_id,
                        "party_name_ja": party_name_ja,
                        "items": items,
                    }
                ],
            }

    # Another common report format: {metadata, party, topics:[{topic_id, excerpts:[...]}]}
    if isinstance(payload.get("metadata"), dict) and isinstance(payload.get("party"), dict) and isinstance(payload.get("topics"), list):
        party = payload.get("party") or {}
        party_id = (party or {}).get("party_id")
        party_name_ja = (party or {}).get("party_name_ja") or (party or {}).get("name_ja")
        generator = "manual"

        items: list[dict[str, Any]] = []
        for t in payload.get("topics") or []:
            if not isinstance(t, dict):
                continue
            topic_id = str(t.get("topic_id") or "").strip()
            excerpts = t.get("excerpts")
            if not isinstance(excerpts, list):
                continue
            for ex in excerpts:
                if not isinstance(ex, dict):
                    continue
                url = _clean_url(ex.get("url"))
                if not url:
                    continue
                items.append(
                    {
                        "source_url": url,
                        "source_title": str(ex.get("document_title") or "").strip() or None,
                        "fetched_at": ex.get("fetched_at") or payload.get("metadata", {}).get("fetch_time_local") or payload.get("metadata", {}).get("fetch_time_utc"),
                        "source_type": str(ex.get("source_type") or "").strip() or None,
                        "topic_ids": [topic_id] if topic_id else [],
                        "quote": ex.get("quote") or "",
                        "claim": ex.get("claim_ja") or ex.get("claim") or "",
                        "quote_context": str(t.get("topic_summary_ja") or "").strip(),
                        "deprecated": bool(ex.get("deprecated") is True),
                        "deprecated_reason": ex.get("deprecated_reason") or None,
                        "citations": ex.get("citations"),
                    }
                )

        return {
            "format": "partyviz_research_pack",
            "version": 1,
            "generated_at": payload.get("metadata", {}).get("fetch_time_local") or payload.get("metadata", {}).get("fetch_time_utc"),
            "generator": generator,
            "parties": [
                {
                    "party_id": party_id,
                    "party_name_ja": party_name_ja,
                    "items": items,
                }
            ],
        }

    # Another common report format: {schema_version, metadata, party_id, party_name, topics:{...}}
    # - topics is a dict keyed by arbitrary ids, each has {topic_id, topic_name_ja, excerpts:[...]}
    if (
        isinstance(payload.get("schema_version"), str)
        and isinstance(payload.get("metadata"), dict)
        and isinstance(payload.get("topics"), dict)
    ):
        metadata = payload.get("metadata") or {}
        meta_party = metadata.get("party") if isinstance(metadata.get("party"), dict) else {}
        top_party = payload.get("party") if isinstance(payload.get("party"), dict) else {}
        party_id = payload.get("party_id") or (top_party or {}).get("party_id") or (meta_party or {}).get("party_id")
        party_name_ja = (
            payload.get("party_name_ja")
            or payload.get("party_name")
            or (top_party or {}).get("party_name_ja")
            or (top_party or {}).get("name_ja")
            or (meta_party or {}).get("name_ja")
            or (meta_party or {}).get("party_name_ja")
        )
        if party_id is None and (not isinstance(party_name_ja, str) or not party_name_ja.strip()):
            raise ValueError("invalid format: missing party fields for schema_version/topics object")
        generator = "manual"

        fetched_at = metadata.get("fetch_time_local") or metadata.get("fetch_time") or metadata.get("fetch_time_utc")

        items: list[dict[str, Any]] = []
        topics_obj = payload.get("topics") or {}
        for _, t in topics_obj.items():
            if not isinstance(t, dict):
                continue
            topic_id = str(t.get("topic_id") or "").strip()
            topic_name_ja = str(t.get("topic_name_ja") or "").strip()
            excerpts = t.get("excerpts")
            if not isinstance(excerpts, list):
                continue
            for ex in excerpts:
                if not isinstance(ex, dict):
                    continue
                url = _clean_url(ex.get("source_url") or ex.get("url"))
                if not url:
                    continue
                items.append(
                    {
                        "source_url": url,
                        "source_title": None,
                        "fetched_at": fetched_at,
                        "source_type": str(ex.get("content_type") or ex.get("source_type") or "").strip() or None,
                        "topic_ids": [topic_id] if topic_id else [],
                        "quote": ex.get("quote") or "",
                        "claim": ex.get("claim_ja") or ex.get("claim") or "",
                        "quote_context": topic_name_ja,
                        "deprecated": bool(ex.get("deprecated") is True),
                        "deprecated_reason": ex.get("deprecated_reason") or None,
                    }
                )

        return {
            "format": "partyviz_research_pack",
            "version": 1,
            "generated_at": fetched_at,
            "generator": generator,
            "parties": [
                {
                    "party_id": party_id,
                    "party_name_ja": party_name_ja,
                    "items": items,
                }
            ],
        }

    # Another common report format: {schema_version, metadata:{party:{...}}, topics:[{topic_id, excerpts:[...]}]}
    # Example: kokumin_policy_research_pack_v1
    if isinstance(payload.get("schema_version"), str) and isinstance(payload.get("metadata"), dict) and isinstance(payload.get("topics"), list):
        meta = payload.get("metadata") or {}
        meta_party = meta.get("party") if isinstance(meta.get("party"), dict) else {}
        party_name_ja = (meta_party or {}).get("name_ja") or (meta_party or {}).get("party_name_ja") or payload.get("party_name")
        party_id = payload.get("party_id")  # often absent; name-based resolution will be used
        generated_at = meta.get("generated_at_jst") or meta.get("fetch_time_local") or meta.get("fetch_time") or meta.get("fetch_time_utc")
        generator = "manual"

        items: list[dict[str, Any]] = []
        for t in payload.get("topics") or []:
            if not isinstance(t, dict):
                continue
            topic_id = str(t.get("topic_id") or "").strip()
            excerpts = t.get("excerpts")
            if not isinstance(excerpts, list):
                continue
            for ex in excerpts:
                if not isinstance(ex, dict):
                    continue
                url = _clean_url(ex.get("url") or ex.get("source_url"))
                if not url:
                    continue
                citations = ex.get("evidence")
                citations_list = [citations] if isinstance(citations, str) and citations.strip() else None
                items.append(
                    {
                        "source_url": url,
                        "source_title": str(ex.get("document_title") or "").strip() or None,
                        "fetched_at": ex.get("fetched_at") or generated_at,
                        "source_type": str(ex.get("source_type") or "").strip() or None,
                        "topic_ids": [topic_id] if topic_id else [],
                        "quote": ex.get("quote_ja") or ex.get("quote") or "",
                        "claim": ex.get("stance_claim_ja") or ex.get("claim_ja") or ex.get("claim") or "",
                        "quote_context": str(t.get("topic_summary_ja") or t.get("notes_ja") or "").strip(),
                        "deprecated": bool(ex.get("deprecated") is True),
                        "deprecated_reason": ex.get("deprecated_reason_ja") or ex.get("deprecated_reason") or None,
                        "citations": citations_list,
                    }
                )

        return {
            "format": "partyviz_research_pack",
            "version": 1,
            "generated_at": generated_at,
            "generator": generator,
            "parties": [
                {
                    "party_id": party_id,
                    "party_name_ja": party_name_ja,
                    "items": items,
                }
            ],
        }

    # Another compact format: {party_id, party_name, fetch_time, topics:[{id, quotes:[{quote,url}], summary_ja}]}
    # Example: sanseito / 手作業まとめ
    if (
        (payload.get("party_id") is not None)
        and (payload.get("party_name") is not None or payload.get("party_name_ja") is not None)
        and isinstance(payload.get("topics"), list)
    ):
        party_id = payload.get("party_id")
        party_name_ja = payload.get("party_name_ja") or payload.get("party_name")
        generated_at = payload.get("fetch_time") or payload.get("generated_at") or payload.get("generated_at_jst")
        generator = "manual"

        def _split_numeric_citations(text: str) -> tuple[str, list[str] | None]:
            lines = [ln.strip() for ln in (text or "").splitlines()]
            cite_nums = [ln for ln in lines if re.fullmatch(r"\d{1,3}", ln)]
            kept = [ln for ln in lines if not re.fullmatch(r"\d{1,3}", ln)]
            cleaned = "\n".join([ln for ln in kept if ln]).strip()
            if cite_nums:
                return cleaned, cite_nums
            return cleaned, None

        items: list[dict[str, Any]] = []
        for t in payload.get("topics") or []:
            if not isinstance(t, dict):
                continue
            topic_id = str(t.get("id") or t.get("topic_id") or "").strip()
            topic_summary = str(t.get("summary_ja") or t.get("summary") or "").strip()
            quotes = t.get("quotes")
            if not isinstance(quotes, list):
                continue
            for q in quotes:
                if not isinstance(q, dict):
                    continue
                url = _clean_url(q.get("url") or q.get("source_url"))
                if not url:
                    continue
                quote_raw = str(q.get("quote") or q.get("quote_ja") or "")
                quote_clean, citations_list = _split_numeric_citations(quote_raw)
                items.append(
                    {
                        "source_url": url,
                        "source_title": None,
                        "fetched_at": generated_at,
                        "source_type": None,
                        "topic_ids": [topic_id] if topic_id else [],
                        "quote": quote_clean,
                        "claim": topic_summary,
                        "quote_context": topic_summary,
                        "deprecated": False,
                        "deprecated_reason": None,
                        "citations": citations_list,
                    }
                )

        return {
            "format": "partyviz_research_pack",
            "version": 1,
            "generated_at": generated_at,
            "generator": generator,
            "parties": [
                {
                    "party_id": party_id,
                    "party_name_ja": party_name_ja,
                    "items": items,
                }
            ],
        }

    keys = sorted([str(k) for k in payload.keys()])
    schema_version = payload.get("schema_version")
    topics_type = type(payload.get("topics")).__name__
    has_schema = isinstance(payload.get("schema"), dict)
    has_party = isinstance(payload.get("party"), dict) or (isinstance(payload.get("metadata"), dict) and isinstance(payload.get("metadata", {}).get("party"), dict))
    raise ValueError(
        "invalid format (expected partyviz_research_pack)"
        + f"; schema_version={schema_version!r}, topics_type={topics_type}, has_schema={has_schema}, has_party={has_party}, keys={keys}"
    )
