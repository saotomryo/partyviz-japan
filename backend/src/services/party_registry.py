from __future__ import annotations

from typing import Iterable, List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models
from ..schemas import PartyCreate, PartyUpdate


def list_parties(db: Session) -> List[models.PartyRegistry]:
    stmt = select(models.PartyRegistry).order_by(models.PartyRegistry.created_at.desc())
    return list(db.scalars(stmt))


def get_party(db: Session, party_id) -> models.PartyRegistry | None:
    return db.get(models.PartyRegistry, party_id)


def update_party(db: Session, party_id, payload: PartyUpdate) -> models.PartyRegistry:
    party = db.get(models.PartyRegistry, party_id)
    if not party:
        raise ValueError("party not found")

    if payload.name_ja is not None:
        party.name_ja = payload.name_ja
    if payload.name_en is not None:
        party.name_en = payload.name_en
    if payload.official_home_url is not None:
        party.official_home_url = payload.official_home_url
    if payload.allowed_domains is not None:
        party.allowed_domains = payload.allowed_domains
    if payload.confidence is not None:
        party.confidence = payload.confidence
    if payload.status is not None:
        party.status = payload.status
    if payload.evidence is not None:
        party.evidence = payload.evidence

    db.commit()
    db.refresh(party)
    return party


def _canonicalize_name_ja(name_ja: str) -> str:
    return "".join(name_ja.split()).lower()


def _merge_unique(existing: Iterable[str], incoming: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for item in list(existing) + list(incoming):
        v = (item or "").strip()
        if not v:
            continue
        if v in seen:
            continue
        seen.add(v)
        merged.append(v)
    return merged


def upsert_party(db: Session, payload: PartyCreate) -> Tuple[models.PartyRegistry, str]:
    """
    name_ja をキーに PartyRegistry を upsert する。
    Returns: (party, action) where action is "created" or "updated".
    """
    canonical = _canonicalize_name_ja(payload.name_ja)
    party = db.scalar(select(models.PartyRegistry).where(models.PartyRegistry.canonical_key == canonical))
    action = "updated"
    if not party:
        party = models.PartyRegistry(
            name_ja=payload.name_ja,
            name_en=payload.name_en,
            official_home_url=payload.official_home_url,
            allowed_domains=payload.allowed_domains,
            confidence=payload.confidence,
            status=payload.status,
            evidence=payload.evidence or {},
        )
        db.add(party)
        action = "created"
    else:
        party.name_ja = payload.name_ja
        if payload.name_en is not None:
            party.name_en = payload.name_en
        if payload.official_home_url is not None:
            party.official_home_url = payload.official_home_url
        party.allowed_domains = _merge_unique(party.allowed_domains or [], payload.allowed_domains or [])
        party.confidence = max(float(party.confidence or 0.0), float(payload.confidence or 0.0))
        party.status = payload.status
        if payload.evidence:
            if isinstance(party.evidence, dict) and isinstance(payload.evidence, dict):
                party.evidence = {**party.evidence, **payload.evidence}
            else:
                party.evidence = payload.evidence

    db.commit()
    db.refresh(party)
    return party, action


def create_party(db: Session, payload: PartyCreate) -> models.PartyRegistry:
    party = models.PartyRegistry(
        name_ja=payload.name_ja,
        name_en=payload.name_en,
        official_home_url=payload.official_home_url,
        allowed_domains=payload.allowed_domains,
        confidence=payload.confidence,
        status=payload.status,
        evidence=payload.evidence or {},
    )
    db.add(party)
    db.commit()
    db.refresh(party)
    return party
