from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import models
from ..schemas import PartyCreate


def list_parties(db: Session) -> List[models.PartyRegistry]:
    stmt = select(models.PartyRegistry).order_by(models.PartyRegistry.created_at.desc())
    return list(db.scalars(stmt))


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
