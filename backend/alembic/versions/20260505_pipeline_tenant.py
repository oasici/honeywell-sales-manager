"""Round-5 R5-TEN-26 — add tenant_id to pipelines.

Pre-R5, pipeline rows were globally readable + writable. Manager in
tenant A could read tenant B's pipelines list, mutate stages, or
delete (causing tenant B's opportunities to lose pipeline references).

Backfill: tenant_id = users.tenant_id of pipelines.created_by. Rows
where the creator's tenant is NULL stay NULL (single-tenant deploy).

Revision ID: 20260505_pipeline_tenant
Revises: 20260504_dead_letter
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260505_pipeline_tenant"
down_revision = "20260504_dead_letter"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE pipelines ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pipeline_tenant ON pipelines (tenant_id)"
    )
    # Backfill from creator's tenant. Idempotent — re-running the
    # migration after partial completion picks up rows still NULL.
    op.execute(
        """
        UPDATE pipelines p
        SET tenant_id = (
            SELECT u.tenant_id FROM users u WHERE u.id = p.created_by
        )
        WHERE tenant_id IS NULL AND created_by IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pipeline_tenant")
    op.execute("ALTER TABLE pipelines DROP COLUMN IF EXISTS tenant_id")
