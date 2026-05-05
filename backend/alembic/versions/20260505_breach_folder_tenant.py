"""Round-5 R5-TEN-28 — add tenant_id to breach_notifications and report_folders.

Pre-R5:
- ``BreachNotification`` had no tenant_id, so a compliance officer in
  tenant A could list every breach record across the database via
  ``GET /compliance/breaches``.
- ``ReportFolder`` had no tenant_id, so ``is_shared=True`` folders
  silently leaked across tenants.

Backfill strategy:
- breach_notifications.tenant_id ← users.tenant_id of created_by.
- report_folders.tenant_id ← users.tenant_id of owner_id.

Rows whose creator/owner has NULL tenant (single-tenant deployments)
stay NULL; downstream scoped_for_user is a no-op when both sides
are None.

Revision ID: 20260505_breach_folder_tenant
Revises: 20260505_pipeline_tenant
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260505_breach_folder_tenant"
down_revision = "20260505_pipeline_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE breach_notifications ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_breach_tenant ON breach_notifications (tenant_id)"
    )
    op.execute(
        """
        UPDATE breach_notifications b
        SET tenant_id = (SELECT u.tenant_id FROM users u WHERE u.id = b.created_by)
        WHERE tenant_id IS NULL AND created_by IS NOT NULL
        """
    )

    op.execute(
        "ALTER TABLE report_folders ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_report_folder_tenant ON report_folders (tenant_id)"
    )
    op.execute(
        """
        UPDATE report_folders f
        SET tenant_id = (SELECT u.tenant_id FROM users u WHERE u.id = f.owner_id)
        WHERE tenant_id IS NULL AND owner_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_report_folder_tenant")
    op.execute("ALTER TABLE report_folders DROP COLUMN IF EXISTS tenant_id")

    op.execute("DROP INDEX IF EXISTS ix_breach_tenant")
    op.execute("ALTER TABLE breach_notifications DROP COLUMN IF EXISTS tenant_id")
