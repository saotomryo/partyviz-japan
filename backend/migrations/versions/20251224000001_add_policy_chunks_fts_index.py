"""add policy_chunks fts index

Revision ID: 20251224000001
Revises: 20251223000000
Create Date: 2025-12-24 00:00:01
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20251224000001"
down_revision = "20251223000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_policy_chunks_content_fts
        ON policy_chunks
        USING gin (to_tsvector('simple', content))
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_policy_chunks_content_fts")
