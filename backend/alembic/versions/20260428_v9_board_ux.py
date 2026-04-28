"""V9 board UX: WIP limits + bulk review queue

Revision ID: 20260428_v9_board_ux
Revises: 20260428_v9_calendar_oauth
Create Date: 2026-04-28

V2 Faz 3.0 backlog #3 (kanban WIP limits) + #4 (bulk stage update review queue).

Idempotent.
"""

from alembic import op


revision = "20260428_v9_board_ux"
down_revision = "20260428_v9_calendar_oauth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE stage_configs ADD COLUMN IF NOT EXISTS wip_limit INTEGER")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_review_queue (
            id SERIAL PRIMARY KEY,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            suggested_stage VARCHAR(30),
            suggested_close_date DATE,
            suggested_amount DOUBLE PRECISION,
            suggestion_source VARCHAR(40) NOT NULL DEFAULT 'rule',
            evidence_json TEXT,
            suggested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            decided_at TIMESTAMPTZ,
            decision VARCHAR(20),
            decided_by INTEGER REFERENCES users(id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pipeline_review_queue_decided_opp ON pipeline_review_queue (decided_at, opportunity_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pipeline_review_queue")
    op.execute("ALTER TABLE stage_configs DROP COLUMN IF EXISTS wip_limit")
