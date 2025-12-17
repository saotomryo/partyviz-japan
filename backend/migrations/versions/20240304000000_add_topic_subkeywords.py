"""add topic search_subkeywords

Revision ID: 20240304000000
Revises: 20240303000000
Create Date: 2024-03-04 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20240304000000"
down_revision: Union[str, None] = "20240303000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
    ALTER TABLE topics
      ADD COLUMN IF NOT EXISTS search_subkeywords JSONB NOT NULL DEFAULT '[]'::jsonb;
    """
    )


def downgrade() -> None:
    op.execute(
        """
    ALTER TABLE topics
      DROP COLUMN IF EXISTS search_subkeywords;
    """
    )

