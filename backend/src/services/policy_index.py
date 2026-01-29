from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import models


@dataclass
class PolicyChunkHit:
    chunk: models.PolicyChunk
    rank: float


def _normalize_queries(queries: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        qn = " ".join((q or "").split())
        if not qn or qn in seen:
            continue
        seen.add(qn)
        out.append(qn)
    return out


def search_policy_chunks(
    db: Session,
    *,
    party_id,
    queries: Sequence[str],
    per_query: int = 3,
    max_total: int = 6,
) -> list[PolicyChunkHit]:
    norm_queries = _normalize_queries(queries)
    if not norm_queries:
        return []

    hits: dict[str, PolicyChunkHit] = {}
    tsv = func.to_tsvector("simple", models.PolicyChunk.content)
    non_deprecated = func.coalesce(models.PolicyChunk.meta.op("->>")("deprecated"), "false") != "true"
    for q in norm_queries:
        tsq = func.plainto_tsquery("simple", q)
        rank = func.ts_rank_cd(tsv, tsq)
        stmt = (
            select(models.PolicyChunk, rank.label("rank"))
            .where(models.PolicyChunk.party_id == party_id)
            .where(non_deprecated)
            .where(tsv.op("@@")(tsq))
            .order_by(rank.desc())
            .limit(max(1, int(per_query)))
        )
        rows = db.execute(stmt).all()
        if not rows:
            ilike_stmt = (
                select(models.PolicyChunk)
                .where(models.PolicyChunk.party_id == party_id)
                .where(non_deprecated)
                .where(models.PolicyChunk.content.ilike(f"%{q}%"))
                .limit(max(1, int(per_query)))
            )
            rows = [(chunk, 0.0) for chunk in db.scalars(ilike_stmt).all()]
        for chunk, score_val in rows:
            score = float(score_val or 0.0)
            key = str(chunk.chunk_id)
            existing = hits.get(key)
            if existing and existing.rank >= score:
                continue
            hits[key] = PolicyChunkHit(chunk=chunk, rank=score)

    ordered = sorted(hits.values(), key=lambda h: h.rank, reverse=True)
    return ordered[: max(1, int(max_total))]
