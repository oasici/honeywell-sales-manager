"""V8 multi-tenant CRM core: tenant_id on users/customers/opportunities/quotes/leads

Revision ID: 20260427_v8_crm_tenant_id
Revises: 20260427_v8_text_embedding
Create Date: 2026-04-27

V7 added tenant_id to 8 V5/V6 *analytics* tables. V8 brings the
boundary into the CRM core. Every column is nullable + indexed —
single-tenant deployments keep working unchanged.

The bootstrap script ``scripts/bootstrap_default_tenant.py`` flips
NULL rows to a default tenant id so even mixed-tenant deployments
don't lose data.

Idempotent.
"""

from alembic import op


revision = "20260427_v8_crm_tenant_id"
down_revision = "20260427_v8_text_embedding"
branch_labels = None
depends_on = None


_CORE_TABLES = ("users", "customers", "opportunities", "quotes", "leads")


def upgrade() -> None:
    for table in _CORE_TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id ON {table} (tenant_id)"
        )


def downgrade() -> None:
    for table in _CORE_TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")
