"""Round-15 F-002 / Sprint 15j cohort 9 — defense-in-depth tenant_id on derived entities.

Continues the cohort 1-8 pattern. This revision covers four child
tables with different parents:

  * ``deal_rooms`` — opportunity-derived collaboration room
    (backfill from ``opportunities.tenant_id``).
  * ``quote_items`` — line items on a quote
    (backfill from ``quotes.tenant_id``).
  * ``meeting_links`` — per-user scheduling templates
    (backfill from the owning ``users.tenant_id``).
  * ``dashboard_configs`` — per-user dashboard layouts
    (backfill from ``users.tenant_id`` via the ``owner_id`` column).

Nullable on disk per the cohort convention so the migration is
non-breaking and reversible.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement.

Revision ID: 20260530_phase12_tenant_did_cohort9
Revises: 20260529_phase12_tenant_did_cohort8
Create Date: 2026-05-14
"""

from __future__ import annotations

from alembic import op


revision = "20260530_phase12_tenant_did_cohort9"
down_revision = "20260529_phase12_tenant_did_cohort8"
branch_labels = None
depends_on = None


# (child_table, parent_table, fk_column_on_child)
_TABLES: list[tuple[str, str, str]] = [
    ("deal_rooms", "opportunities", "opportunity_id"),
    ("quote_items", "quotes", "quote_id"),
    ("meeting_links", "users", "user_id"),
    ("dashboard_configs", "users", "owner_id"),
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
