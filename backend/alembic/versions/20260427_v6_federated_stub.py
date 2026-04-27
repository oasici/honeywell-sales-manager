"""V6 federated benchmark stub

Revision ID: 20260427_v6_federated_stub
Revises: 20260427_v6_replay_deltas
Create Date: 2026-04-27

Lays the schema for cross-tenant benchmarks before we go multi-tenant
so privacy controls aren't retrofitted later. The table is dormant
until ``FederatedBenchmarkService.publish_benchmark`` starts being
called from a real tenant aggregator.
"""

from alembic import op


revision = "20260427_v6_federated_stub"
down_revision = "20260427_v6_replay_deltas"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS federated_benchmarks (
            id SERIAL PRIMARY KEY,
            benchmark_key VARCHAR(120) NOT NULL,
            snapshot_date DATE NOT NULL,
            metric_name VARCHAR(60) NOT NULL,
            metric_value DOUBLE PRECISION,
            sample_bucket VARCHAR(40),
            privacy_level VARCHAR(20) NOT NULL DEFAULT 'aggregate_k_anon',
            tenant_count INTEGER NOT NULL DEFAULT 0,
            sample_size INTEGER NOT NULL DEFAULT 0,
            suppressed BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_federated_benchmarks_key_date ON federated_benchmarks (benchmark_key, snapshot_date)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS federated_benchmarks")
