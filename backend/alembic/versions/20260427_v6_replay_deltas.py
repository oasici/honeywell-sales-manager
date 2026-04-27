"""V6 deal replay deltas

Revision ID: 20260427_v6_replay_deltas
Revises: 20260427_v6_core_depth
Create Date: 2026-04-27

Adds ``deal_replay_deltas`` — pairwise diff rows between
``opportunity_features_daily`` snapshots, with a rule-based
``counterfactual_hint`` so the rep UI can render a one-liner like
"3 days passed after quote_sent without follow-up".

Idempotent (``CREATE TABLE IF NOT EXISTS``).
"""

from alembic import op


revision = "20260427_v6_replay_deltas"
down_revision = "20260427_v6_core_depth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS deal_replay_deltas (
            id SERIAL PRIMARY KEY,
            opportunity_id INTEGER NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
            from_ts TIMESTAMPTZ NOT NULL,
            to_ts TIMESTAMPTZ NOT NULL,
            change_type VARCHAR(40) NOT NULL,
            change_summary TEXT,
            impact_score DOUBLE PRECISION,
            drivers_json TEXT,
            counterfactual_hint VARCHAR(80),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_deal_replay_deltas_opp_to_ts ON deal_replay_deltas (opportunity_id, to_ts)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS deal_replay_deltas")
