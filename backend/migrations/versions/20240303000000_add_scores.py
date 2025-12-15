"""add score_runs and topic_scores

Revision ID: 20240303000000
Revises: 20240302000000
Create Date: 2024-03-03 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20240303000000"
down_revision: Union[str, None] = "20240302000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
    CREATE TABLE IF NOT EXISTS score_runs (
      run_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      topic_id        TEXT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,

      search_provider TEXT,
      search_model    TEXT,
      score_provider  TEXT,
      score_model     TEXT,

      meta            JSONB NOT NULL DEFAULT '{}'::jsonb,
      created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """
    )

    op.execute("CREATE INDEX IF NOT EXISTS idx_score_runs_topic_id_created_at ON score_runs(topic_id, created_at DESC);")

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS topic_scores (
      score_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      run_id         UUID NOT NULL REFERENCES score_runs(run_id) ON DELETE CASCADE,
      topic_id       TEXT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
      party_id       UUID NOT NULL REFERENCES party_registry(party_id) ON DELETE CASCADE,

      stance_label   TEXT NOT NULL,
      stance_score   INT NOT NULL,
      confidence     NUMERIC(4,3) NOT NULL DEFAULT 0.000,
      rationale      TEXT NOT NULL DEFAULT '',

      evidence_url   TEXT,
      evidence_quote TEXT,
      evidence       JSONB NOT NULL DEFAULT '[]'::jsonb,

      created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """
    )

    op.execute("CREATE INDEX IF NOT EXISTS idx_topic_scores_run_id ON topic_scores(run_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_topic_scores_topic_party ON topic_scores(topic_id, party_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_topic_scores_created_at ON topic_scores(created_at DESC);")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS topic_scores;")
    op.execute("DROP TABLE IF EXISTS score_runs;")

