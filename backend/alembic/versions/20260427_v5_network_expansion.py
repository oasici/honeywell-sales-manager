"""V5 network expansion: network_patterns + network_anomalies

Revision ID: 20260427_v5_network_expansion
Revises: 20260427_v5_dna_patterns
Create Date: 2026-04-27

Segment-level pattern + anomaly stores. `segment_benchmarks_daily`
already provides the rolling means; these tables capture (a) the
mined behavioural patterns at the segment level and (b) z-score
anomalies on those benchmarks.
"""

from alembic import op


revision = "20260427_v5_network_expansion"
down_revision = "20260427_v5_dna_patterns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS network_patterns (
            id SERIAL PRIMARY KEY,
            segment_key VARCHAR(80) NOT NULL,
            pattern_type VARCHAR(40) NOT NULL,
            pattern_json TEXT NOT NULL DEFAULT '{}',
            performance_metric VARCHAR(40) NOT NULL,
            metric_value DOUBLE PRECISION NOT NULL DEFAULT 0,
            sample_size INTEGER NOT NULL DEFAULT 0,
            confidence_score DOUBLE PRECISION NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_network_patterns_segment "
        "ON network_patterns (segment_key)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS network_anomalies (
            id SERIAL PRIMARY KEY,
            segment_key VARCHAR(80) NOT NULL,
            metric_name VARCHAR(60) NOT NULL,
            expected_value DOUBLE PRECISION NOT NULL,
            actual_value DOUBLE PRECISION NOT NULL,
            z_score DOUBLE PRECISION NOT NULL,
            severity VARCHAR(10) NOT NULL DEFAULT 'med',
            explanation_json TEXT,
            detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            resolved_at TIMESTAMPTZ
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_network_anomalies_segment_detected "
        "ON network_anomalies (segment_key, detected_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS network_anomalies")
    op.execute("DROP TABLE IF EXISTS network_patterns")
