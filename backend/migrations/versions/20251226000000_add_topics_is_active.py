"""add topics is_active

Revision ID: 20251226000000
Revises: 20251224000001
Create Date: 2025-12-26 00:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20251226000000"
down_revision = "20251224000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("topics", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
    op.execute("UPDATE topics SET is_active = true WHERE is_active IS NULL")


def downgrade() -> None:
    op.drop_column("topics", "is_active")
