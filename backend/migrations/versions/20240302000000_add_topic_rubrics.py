"""add topics and topic_rubrics

Revision ID: 20240302000000
Revises: 20240301000000
Create Date: 2024-03-02 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20240302000000"
down_revision: Union[str, None] = "20240301000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
    DO $$ BEGIN
      CREATE TYPE rubric_status AS ENUM ('draft', 'active', 'archived');
    EXCEPTION
      WHEN duplicate_object THEN NULL;
    END $$;
    """
    )

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS topics (
      topic_id     TEXT PRIMARY KEY,
      name         TEXT NOT NULL,
      description  TEXT,
      created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """
    )

    op.execute("CREATE INDEX IF NOT EXISTS idx_topics_name ON topics(name);")

    op.execute(
        """
    CREATE TABLE IF NOT EXISTS topic_rubrics (
      rubric_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
      topic_id        TEXT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
      version         INT NOT NULL DEFAULT 1,
      status          rubric_status NOT NULL DEFAULT 'draft',

      axis_a_label    TEXT NOT NULL,
      axis_b_label    TEXT NOT NULL,
      steps           JSONB NOT NULL DEFAULT '[]'::jsonb,

      generated_by    TEXT,
      llm_provider    TEXT,
      llm_model       TEXT,
      prompt_version  TEXT,

      created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

      UNIQUE(topic_id, version)
    );
    """
    )

    op.execute("CREATE INDEX IF NOT EXISTS idx_topic_rubrics_topic_id ON topic_rubrics(topic_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_topic_rubrics_status ON topic_rubrics(status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_topic_rubrics_steps_gin ON topic_rubrics USING GIN (steps);")

    op.execute("DROP TRIGGER IF EXISTS trg_topics_updated_at ON topics;")
    op.execute(
        """
    CREATE TRIGGER trg_topics_updated_at
    BEFORE UPDATE ON topics
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """
    )

    op.execute("DROP TRIGGER IF EXISTS trg_topic_rubrics_updated_at ON topic_rubrics;")
    op.execute(
        """
    CREATE TRIGGER trg_topic_rubrics_updated_at
    BEFORE UPDATE ON topic_rubrics
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_topic_rubrics_updated_at ON topic_rubrics;")
    op.execute("DROP TRIGGER IF EXISTS trg_topics_updated_at ON topics;")
    op.execute("DROP TABLE IF EXISTS topic_rubrics;")
    op.execute("DROP TABLE IF EXISTS topics;")
    op.execute("DROP TYPE IF EXISTS rubric_status;")

