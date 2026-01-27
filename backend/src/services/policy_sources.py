from __future__ import annotations

from typing import Iterable
from urllib.parse import urlparse

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..db import models


def _normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return ""
    # Common copy/paste artifacts from JSON/HTML attributes
    u = u.strip().strip('\'"')
    if u.endswith("/"):
        return u
    return u + "/"


def _domain_allowed(netloc: str, allowed_domains: list[str]) -> bool:
    host = (netloc or "").split(":")[0].lower()
    allowed = [d.split(":")[0].lower() for d in (allowed_domains or []) if d]
    if not host or not allowed:
        return False
    if host in allowed:
        return True
    return any(host.endswith("." + d) for d in allowed)


def list_sources(db: Session, party_id) -> list[models.PartyPolicySource]:
    return list(
        db.scalars(
            select(models.PartyPolicySource)
            .where(models.PartyPolicySource.party_id == party_id)
            .order_by(models.PartyPolicySource.created_at.asc())
        )
    )


def replace_sources(db: Session, party_id, base_urls: Iterable[str]) -> list[models.PartyPolicySource]:
    party = db.get(models.PartyRegistry, party_id)
    if not party:
        raise ValueError("party not found")

    allowed_domains = list(party.allowed_domains or [])
    if party.official_home_url:
        try:
            allowed_domains.append(urlparse(party.official_home_url).netloc)
        except ValueError:
            pass

    normalized: list[str] = []
    seen: set[str] = set()
    for u in base_urls:
        url = _normalize_url(str(u or ""))
        if not url or url in seen:
            continue
        try:
            pu = urlparse(url)
        except ValueError:
            continue
        if pu.scheme not in {"http", "https"}:
            continue
        if not _domain_allowed(pu.netloc, allowed_domains):
            continue
        seen.add(url)
        normalized.append(url)

    db.execute(delete(models.PartyPolicySource).where(models.PartyPolicySource.party_id == party_id))
    for url in normalized:
        db.add(models.PartyPolicySource(party_id=party_id, base_url=url, status="active"))
    db.commit()
    return list_sources(db, party_id)
