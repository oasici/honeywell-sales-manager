"""Add tenant_id to billing surfaces (invoices/contracts/subscriptions/revenue)

Revision ID: 20260504_billing_tenant
Revises: 20260503_opp_source_safety
Create Date: 2026-05-04

Round-4 audit R4-CLOSE-1 / R4-TEN-5..8.

The Quote, Customer, Opportunity, and Lead tables have had tenant_id
since V8 (20260427_v8_crm_tenant_id). The billing surfaces (invoices,
contracts, subscriptions, revenue_schedules, revenue_schedule_entries)
shipped without it — meaning every authenticated user could read or
mutate every other tenant's billing data. The round-4 audit caught
nine routes touching these tables with no tenant filter at all (see
the audit report's R4-TEN-5..8 section).

This migration adds the column + index on each table and backfills
from the parent entity:

- invoices.tenant_id ← customers.tenant_id via customer_id FK
- contracts.tenant_id ← customers.tenant_id via customer_id FK
- subscriptions.tenant_id ← customers.tenant_id via customer_id FK
- revenue_schedules.tenant_id ← contracts (already backfilled) via
  contract_id FK
- revenue_schedule_entries.tenant_id ← schedules (already backfilled)
  via schedule_id FK

The backfill is idempotent (only updates rows where tenant_id IS
NULL). On a fresh prod env it's a no-op because the columns are added
without rows.

Idempotent both ways. The downgrade drops the index + column; live
data is preserved on the parent rows so re-applying re-derives.
"""

from alembic import op


revision = "20260504_billing_tenant"
down_revision = "20260503_opp_source_safety"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add the columns + indexes (idempotent).
    for table, index in (
        ("invoices", "ix_invoice_tenant"),
        ("contracts", "ix_contracts_tenant_id"),
        ("subscriptions", "ix_subscriptions_tenant_id"),
        ("revenue_schedules", "ix_rs_tenant"),
        ("revenue_schedule_entries", "ix_rse_tenant"),
    ):
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {index} ON {table} (tenant_id)"
        )

    # 2. Backfill each table from the closest parent that already
    # carries tenant_id. Only updates NULL rows so re-runs are safe.
    op.execute(
        """
        UPDATE invoices
           SET tenant_id = c.tenant_id
          FROM customers c
         WHERE invoices.customer_id = c.id
           AND invoices.tenant_id IS NULL
           AND c.tenant_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE contracts
           SET tenant_id = c.tenant_id
          FROM customers c
         WHERE contracts.customer_id = c.id
           AND contracts.tenant_id IS NULL
           AND c.tenant_id IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE subscriptions
           SET tenant_id = c.tenant_id
          FROM customers c
         WHERE subscriptions.customer_id = c.id
           AND subscriptions.tenant_id IS NULL
           AND c.tenant_id IS NOT NULL
        """
    )
    # Revenue schedules ride on the contract (which now has tenant_id).
    op.execute(
        """
        UPDATE revenue_schedules
           SET tenant_id = c.tenant_id
          FROM contracts c
         WHERE revenue_schedules.contract_id = c.id
           AND revenue_schedules.tenant_id IS NULL
           AND c.tenant_id IS NOT NULL
        """
    )
    # Entries inherit from their parent schedule.
    op.execute(
        """
        UPDATE revenue_schedule_entries rse
           SET tenant_id = rs.tenant_id
          FROM revenue_schedules rs
         WHERE rse.schedule_id = rs.id
           AND rse.tenant_id IS NULL
           AND rs.tenant_id IS NOT NULL
        """
    )


def downgrade() -> None:
    for table, index in (
        ("revenue_schedule_entries", "ix_rse_tenant"),
        ("revenue_schedules", "ix_rs_tenant"),
        ("subscriptions", "ix_subscriptions_tenant_id"),
        ("contracts", "ix_contracts_tenant_id"),
        ("invoices", "ix_invoice_tenant"),
    ):
        op.execute(f"DROP INDEX IF EXISTS {index}")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")
