"""init schema

Revision ID: 20240301000000
Revises:
Create Date: 2024-03-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20240301000000"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensions and enums
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")

    op.execute(
        """
    DO $$ BEGIN
      CREATE TYPE party_status AS ENUM ('candidate', 'verified', 'needs_review', 'rejected');
    EXCEPTION
      WHEN duplicate_object THEN NULL;
    END $$;
    """
    )

    op.execute(
        """
    DO $$ BEGIN
      CREATE TYPE discovery_action AS ENUM ('added', 'updated', 'removed');
    EXCEPTION
      WHEN duplicate_object THEN NULL;
    END $$;
    """
    )

    op.execute(
        """
    DO $$ BEGIN
      CREATE TYPE evidence_type AS ENUM (
        'official_link_list',
        'election_commission_list',
        'official_site_self_declare',
        'manual_review'
      );
    EXCEPTION
      WHEN duplicate_object THEN NULL;
    END $$;
    """
    )

    # party_registry
    op.execute(
        r"""
    CREATE TABLE IF NOT EXISTS party_registry (
      party_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      name_ja            TEXT NOT NULL,
      name_en            TEXT,
      status             party_status NOT NULL DEFAULT 'candidate',

      official_home_url  TEXT,
      allowed_domains    TEXT[] NOT NULL DEFAULT '{}',

      confidence         NUMERIC(4,3) NOT NULL DEFAULT 0.000,
      evidence           JSONB NOT NULL DEFAULT '[]'::jsonb,

      first_seen_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
      last_checked_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
      verified_at        TIMESTAMPTZ,

      canonical_key      TEXT GENERATED ALWAYS AS (lower(regexp_replace(name_ja, '\\s+', '', 'g'))) STORED,

      created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """
    )

    op.execute("CREATE INDEX IF NOT EXISTS idx_party_registry_status ON party_registry(status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_party_registry_canonical_key ON party_registry(canonical_key);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_party_registry_allowed_domains_gin ON party_registry USING GIN (allowed_domains);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_party_registry_evidence_gin ON party_registry USING GIN (evidence);")

    op.execute(
        """
    CREATE OR REPLACE FUNCTION set_updated_at()
    RETURNS TRIGGER AS $$
    BEGIN
      NEW.updated_at = now();
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    )

    op.execute("DROP TRIGGER IF EXISTS trg_party_registry_updated_at ON party_registry;")
    op.execute(
        """
    CREATE TRIGGER trg_party_registry_updated_at
    BEFORE UPDATE ON party_registry
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """
    )

    # party_discovery_events
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS party_discovery_events (
      event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      source_name     TEXT NOT NULL,
      source_url      TEXT NOT NULL,
      action          discovery_action NOT NULL,
      observed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),

      party_name_ja   TEXT NOT NULL,
      candidate_url   TEXT,
      extracted_text  TEXT,

      payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
      snapshot_hash   TEXT,
      idempotency_key TEXT UNIQUE
    );
    """
    )

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_discovery_events_observed_at ON party_discovery_events(observed_at);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_discovery_events_source_name ON party_discovery_events(source_name);")

    # source_snapshots
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS source_snapshots (
      snapshot_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      source_name     TEXT NOT NULL,
      source_url      TEXT NOT NULL,
      fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
      content_hash    TEXT NOT NULL,
      content         BYTEA,
      meta            JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    """
    )

    op.execute("CREATE INDEX IF NOT EXISTS idx_source_snapshots_source_name ON source_snapshots(source_name);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_source_snapshots_fetched_at ON source_snapshots(fetched_at);")

    # party_change_history
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS party_change_history (
      change_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      party_id      UUID NOT NULL REFERENCES party_registry(party_id) ON DELETE CASCADE,
      changed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
      change_type   TEXT NOT NULL,
      before_state  JSONB NOT NULL,
      after_state   JSONB NOT NULL,
      reason        TEXT,
      evidence      JSONB NOT NULL DEFAULT '[]'::jsonb
    );
    """
    )

    op.execute("CREATE INDEX IF NOT EXISTS idx_party_change_history_party_id ON party_change_history(party_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_party_change_history_changed_at ON party_change_history(changed_at);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS party_change_history;")
    op.execute("DROP TABLE IF EXISTS source_snapshots;")
    op.execute("DROP TABLE IF EXISTS party_discovery_events;")
    op.execute("DROP TRIGGER IF EXISTS trg_party_registry_updated_at ON party_registry;")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
    op.execute("DROP TABLE IF EXISTS party_registry;")
    op.execute("DROP TYPE IF EXISTS evidence_type;")
    op.execute("DROP TYPE IF EXISTS discovery_action;")
    op.execute("DROP TYPE IF EXISTS party_status;")
    op.execute("DROP EXTENSION IF EXISTS pgcrypto;")
