"""V5 timing engine: recommended_action_windows

Revision ID: 20260427_v5_timing_engine
Revises: 20260427_v5_objection_intel
Create Date: 2026-04-27

A timing-engine output table: for every open opportunity the nightly
job writes one row per recommended action with the optimal window
(window_start..window_end) computed from segment medians of historical
won-deal action gaps. Reps see overdue items as critical.
"""

from alembic import op


revision = "20260427_v5_timing_engine"
down_revision = "20260427_v5_objection_intel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS recommended_action_windows (
            id SERIAL PRIMARY KEY,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            action_type VARCHAR(60) NOT NULL,
            window_start TIMESTAMPTZ NOT NULL,
            window_end TIMESTAMPTZ NOT NULL,
            recommended_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expected_uplift DOUBLE PRECISION,
            urgency_score DOUBLE PRECISION,
            reason_codes_json TEXT NOT NULL DEFAULT '[]',
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            done_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_raw_opportunity_status "
        "ON recommended_action_windows (opportunity_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_raw_window_end "
        "ON recommended_action_windows (window_end)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS recommended_action_windows")
