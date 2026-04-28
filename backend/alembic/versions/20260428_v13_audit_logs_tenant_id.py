"""V13: audit_logs.tenant_id for forensics

Revision ID: 20260428_v13_audit_logs_tenant_id
Revises: 20260428_v12_transformer_seq
Create Date: 2026-04-28

Per-tenant audit queries currently require joining audit_logs with
users on user_id, which is slow at scale (audit_logs grows fastest)
and breaks for system actions where user_id is NULL. This migration
denormalises tenant_id onto audit_logs.

The column is nullable + indexed:
- NULL on rows that existed before this migration ran (backfill is
  safe but not strictly required — historical rows aren't queried
  per-tenant in the dashboards).
- Indexed for ``WHERE tenant_id = :tenant`` filters from
  ``/audit/by-tenant`` endpoints.

Idempotent.
"""

from alembic import op


revision = "20260428_v13_audit_logs_tenant_id"
down_revision = "20260428_v12_transformer_seq"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_audit_logs_tenant_id "
        "ON audit_logs (tenant_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_tenant_id")
    op.execute("ALTER TABLE audit_logs DROP COLUMN IF EXISTS tenant_id")
