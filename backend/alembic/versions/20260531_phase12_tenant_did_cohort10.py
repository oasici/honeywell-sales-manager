"""Round-15 F-002 / Sprint 15j cohort 10 — defense-in-depth tenant_id on derived rollups.

Continues the cohort 1-9 pattern. This revision covers five tables
with three distinct parents:

  * ``account_enrichments`` — per-customer cached aggregates
    (backfill from ``customers.tenant_id``).
  * ``user_customer_pins`` — per-(user, customer) pin entry
    (backfill from ``customers.tenant_id``; equally valid via
    users.tenant_id since both must share a tenant by design).
  * ``coaching_plans`` — per-rep coaching plan
    (backfill from ``users.tenant_id`` via ``user_id``).
  * ``coaching_snapshots`` — per-rep score snapshot
    (backfill from ``users.tenant_id`` via ``user_id``).
  * ``playbook_adherence`` — per-(opportunity, playbook step)
    completion row (backfill from ``opportunities.tenant_id``).

Nullable on disk per the cohort convention so the migration is
non-breaking and reversible.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement.

Revision ID: 20260531_phase12_tenant_did_cohort10
Revises: 20260530_phase12_tenant_did_cohort9
Create Date: 2026-05-14
"""

from __future__ import annotations

from alembic import op


revision = "20260531_phase12_tenant_did_cohort10"
down_revision = "20260530_phase12_tenant_did_cohort9"
branch_labels = None
depends_on = None


# (child_table, parent_table, fk_column_on_child)
_TABLES: list[tuple[str, str, str]] = [
    ("account_enrichments", "customers", "customer_id"),
    ("user_customer_pins", "customers", "customer_id"),
    ("coaching_plans", "users", "user_id"),
    ("coaching_snapshots", "users", "user_id"),
    ("playbook_adherence", "opportunities", "opportunity_id"),
]


def upgrade() -> None:
    for table, parent, fk_col in _TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
        )
        op.execute(
            f"""
            UPDATE {table} c
            SET tenant_id = p.tenant_id
            FROM {parent} p
            WHERE c.tenant_id IS NULL
              AND c.{fk_col} = p.id
              AND p.tenant_id IS NOT NULL
            """
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id "
            f"ON {table} (tenant_id)"
        )


def downgrade() -> None:
    for table, _parent, _fk in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_tenant_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")
