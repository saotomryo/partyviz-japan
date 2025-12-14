from enum import Enum

from sqlalchemy import Computed, Column, Enum as PgEnum, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.types import LargeBinary

from . import Base


class PartyStatus(str, Enum):
    candidate = "candidate"
    verified = "verified"
    needs_review = "needs_review"
    rejected = "rejected"


class DiscoveryAction(str, Enum):
    added = "added"
    updated = "updated"
    removed = "removed"


class EvidenceType(str, Enum):
    official_link_list = "official_link_list"
    election_commission_list = "election_commission_list"
    official_site_self_declare = "official_site_self_declare"
    manual_review = "manual_review"


class PartyRegistry(Base):
    __tablename__ = "party_registry"

    party_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name_ja = Column(Text, nullable=False)
    name_en = Column(Text)
    status = Column(
        PgEnum(PartyStatus, name="party_status", create_type=False),
        nullable=False,
        server_default=text("'candidate'::party_status"),
    )
    official_home_url = Column(Text)
    allowed_domains = Column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    confidence = Column(Numeric(4, 3), nullable=False, server_default=text("0.000"))
    evidence = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    first_seen_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    last_checked_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    verified_at = Column(TIMESTAMP(timezone=True))
    canonical_key = Column(
        Text,
        Computed("lower(regexp_replace(name_ja, '\\\\s+', '', 'g'))", persisted=True),
    )
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))


class PartyDiscoveryEvent(Base):
    __tablename__ = "party_discovery_events"

    event_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_name = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    action = Column(PgEnum(DiscoveryAction, name="discovery_action", create_type=False), nullable=False)
    observed_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    party_name_ja = Column(Text, nullable=False)
    candidate_url = Column(Text)
    extracted_text = Column(Text)
    payload = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    snapshot_hash = Column(Text)
    idempotency_key = Column(Text, unique=True)


class SourceSnapshot(Base):
    __tablename__ = "source_snapshots"

    snapshot_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_name = Column(Text, nullable=False)
    source_url = Column(Text, nullable=False)
    fetched_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    content_hash = Column(Text, nullable=False)
    content = Column(LargeBinary)
    meta = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))


class PartyChangeHistory(Base):
    __tablename__ = "party_change_history"

    change_id = Column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    party_id = Column(UUID(as_uuid=True), ForeignKey("party_registry.party_id", ondelete="CASCADE"), nullable=False)
    changed_at = Column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    change_type = Column(Text, nullable=False)
    before_state = Column(JSONB, nullable=False)
    after_state = Column(JSONB, nullable=False)
    reason = Column(Text)
    evidence = Column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
