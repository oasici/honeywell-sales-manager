"""Round-5 R5-DB-2/3 — drop duplicate tenant_id indexes.

Pre-R5 the signature_requests and webhook_deliveries tables each had
two indexes on tenant_id (one explicit ``ix_sig_tenant`` /
``ix_delivery_tenant`` in __table_args__, plus the implicit one from
``index=True`` on the column). Storage waste + extra write cost,
zero correctness benefit. R5-DB-2/3 dropped ``index=True`` from the
ORM column; this migration removes the auto-named index from prod
DBs that already have it.

Revision ID: 20260505_drop_dup_indexes
Revises: 20260505_breach_folder_tenant
Create Date: 2026-05-05
"""

from __future__ import annotations

from alembic import op


revision = "20260505_drop_dup_indexes"
down_revision = "20260505_breach_folder_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLAlchemy auto-names index=True column indexes as
    # ix_<table>_<column>; drop those, keep the explicit
    # __table_args__ ones (ix_sig_tenant, ix_delivery_tenant).
    op.execute("DROP INDEX IF EXISTS ix_signature_requests_tenant_id")
    op.execute("DROP INDEX IF EXISTS ix_webhook_deliveries_tenant_id")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_signature_requests_tenant_id "
        "ON signature_requests (tenant_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_tenant_id "
        "ON webhook_deliveries (tenant_id)"
    )
