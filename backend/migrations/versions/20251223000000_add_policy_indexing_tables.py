"""add policy indexing tables

Revision ID: 20251223000000
Revises: 20240304000000
Create Date: 2025-12-23 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20251223000000"
down_revision: Union[str, None] = "20240304000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS party_policy_sources (
      source_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      party_id     UUID NOT NULL REFERENCES party_registry(party_id) ON DELETE CASCADE,
      base_url     TEXT NOT NULL,
      status       TEXT NOT NULL DEFAULT 'active',
      created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
      UNIQUE(party_id, base_url)
    );
    """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_party_policy_sources_party_id ON party_policy_sources(party_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_party_policy_sources_status ON party_policy_sources(status);")

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS policy_documents (
      doc_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      party_id      UUID NOT NULL REFERENCES party_registry(party_id) ON DELETE CASCADE,
      url           TEXT NOT NULL UNIQUE,
      doc_type      TEXT NOT NULL,
      title         TEXT,
      content_text  TEXT,
      fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
      hash          TEXT
    );
    """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_policy_documents_party_id ON policy_documents(party_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_policy_documents_type ON policy_documents(doc_type);")

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS policy_chunks (
      chunk_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      doc_id       UUID NOT NULL REFERENCES policy_documents(doc_id) ON DELETE CASCADE,
      party_id     UUID NOT NULL REFERENCES party_registry(party_id) ON DELETE CASCADE,
      chunk_index  INT NOT NULL,
      content      TEXT NOT NULL,
      embedding    TEXT,
      meta         JSONB NOT NULL DEFAULT '{}'::jsonb
    );
    """
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_policy_chunks_party_id ON policy_chunks(party_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_policy_chunks_doc_id ON policy_chunks(doc_id);")

    op.execute("DROP TRIGGER IF EXISTS trg_party_policy_sources_updated_at ON party_policy_sources;")
    op.execute(
        """
    CREATE TRIGGER trg_party_policy_sources_updated_at
    BEFORE UPDATE ON party_policy_sources
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_party_policy_sources_updated_at ON party_policy_sources;")
    op.execute("DROP TABLE IF EXISTS policy_chunks;")
    op.execute("DROP TABLE IF EXISTS policy_documents;")
    op.execute("DROP TABLE IF EXISTS party_policy_sources;")
