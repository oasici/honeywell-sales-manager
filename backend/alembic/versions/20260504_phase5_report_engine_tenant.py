"""Add tenant_id to report_templates (R4-TEN-14)

Revision ID: 20260504_phase5_reports
Revises: 20260504_phase4_tenant
Create Date: 2026-05-04

Round-4 Phase 5. The ReportEngine builds dynamic SELECTs across
Quote/Opportunity/Customer/EmailRequest with no tenant predicate;
the engine now refuses to run when ``current_user`` is missing AND
injects ``WHERE model.tenant_id = current_user.tenant_id`` on every
generated query. ReportTemplate itself also gains tenant_id so
templates can't be enumerated or executed across tenants.

Backfill: report_templates.tenant_id ← users.tenant_id via created_by.
System templates (created_by IS NULL) intentionally remain
tenant-agnostic — they ship with the product and should be visible
to every tenant.

Idempotent both ways.
"""

from alembic import op


revision = "20260504_phase5_reports"
down_revision = "20260504_phase4_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE report_templates ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_report_templates_tenant_id "
        "ON report_templates (tenant_id)"
    )
    # Backfill via created_by (system templates intentionally stay NULL).
    op.execute(
        """
        UPDATE report_templates
           SET tenant_id = u.tenant_id
          FROM users u
         WHERE report_templates.created_by = u.id
           AND report_templates.tenant_id IS NULL
           AND u.tenant_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_report_templates_tenant_id")
    op.execute("ALTER TABLE report_templates DROP COLUMN IF EXISTS tenant_id")
