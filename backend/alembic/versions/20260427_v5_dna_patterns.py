"""V5 sales DNA mining: dna_patterns + dna_recommendations

Revision ID: 20260427_v5_dna_patterns
Revises: 20260427_v5_timing_engine
Create Date: 2026-04-27

Segment-level pattern store. Per-opportunity DNA snapshots already
exist in `v4_sales_dna_snapshots`; these tables hold the *aggregated*
patterns mined across won/lost deals plus the recommendations derived
from them.
"""

from alembic import op


revision = "20260427_v5_dna_patterns"
down_revision = "20260427_v5_timing_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── dna_patterns ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dna_patterns (
            id SERIAL PRIMARY KEY,
            segment_key VARCHAR(80) NOT NULL,
            pattern_name VARCHAR(200) NOT NULL,
            pattern_type VARCHAR(40) NOT NULL,
            sequence_template_json TEXT NOT NULL DEFAULT '[]',
            support_count INTEGER NOT NULL DEFAULT 0,
            win_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
            baseline_win_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
            lift_vs_baseline DOUBLE PRECISION NOT NULL DEFAULT 0,
            confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            last_trained_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dna_patterns_segment_lift "
        "ON dna_patterns (segment_key, lift_vs_baseline DESC)"
    )

    # ── dna_recommendations ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS dna_recommendations (
            id SERIAL PRIMARY KEY,
            segment_key VARCHAR(80) NOT NULL,
            stage_scope VARCHAR(40),
            recommendation_json TEXT NOT NULL,
            source_pattern_id INTEGER REFERENCES dna_patterns(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_dna_recs_segment "
        "ON dna_recommendations (segment_key)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS dna_recommendations")
    op.execute("DROP TABLE IF EXISTS dna_patterns")
