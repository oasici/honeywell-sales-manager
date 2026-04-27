"""V7 tenant boundary on analytics tables

Revision ID: 20260427_v7_tenant_boundary
Revises: 20260427_v7_dna_uplift
Create Date: 2026-04-27

Lays the multi-tenant boundary on the V5/V6 analytics tables so
network/DNA/federated outputs can be tenant-segregated when the CRM
half catches up. CRM-side tables (opportunities, customers, users)
are intentionally untouched — that's a separate, larger migration
project.

All ``tenant_id`` columns are NULLABLE with no FK constraint yet, so
single-tenant deployments keep working unchanged.

Idempotent (``ADD COLUMN IF NOT EXISTS``).
"""

from alembic import op


revision = "20260427_v7_tenant_boundary"
down_revision = "20260427_v7_dna_uplift"
branch_labels = None
depends_on = None


_TARGET_TABLES = (
    "network_segments",
    "segment_benchmarks_daily",
    "dna_patterns",
    "dna_recommendations",
    "network_anomalies",
    "network_patterns",
    "objection_patterns",
    "federated_benchmarks",
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS tenants (
            id SERIAL PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            region VARCHAR(60),
            plan_tier VARCHAR(40) NOT NULL DEFAULT 'standard',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_tenants_name ON tenants (name)"
    )

    for table in _TARGET_TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id ON {table} (tenant_id)"
        )


def downgrade() -> None:
    for table in _TARGET_TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")
    op.execute("DROP TABLE IF EXISTS tenants")
