"""Round-15 Sprint 15q cohort 7 — promote tenant_id NOT NULL on api_keys + deal_similarity_links.

Two more derivatives with clean NOT NULL parent FK chains:

  * ``api_keys``              — user_id NOT NULL → users.tenant_id NOT NULL since R11.
  * ``deal_similarity_links`` — opportunity_id NOT NULL → opportunities.tenant_id NOT NULL since cohort 1.

Standard 4-step asyncpg-safe contract.

Revision ID: 20260611_phase13_tenant_not_null_cohort7
Revises: 20260610_phase14_enum_check_constraints
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op


revision = "20260611_phase13_tenant_not_null_cohort7"
down_revision = "20260610_phase14_enum_check_constraints"
branch_labels = None
depends_on = None


_BACKFILL_PLAN: tuple[tuple[str, str, str, str], ...] = (
    ("api_keys", "users", "user_id", "id"),
    ("deal_similarity_links", "opportunities", "opportunity_id", "id"),
)

_TABLES: tuple[str, ...] = tuple(plan[0] for plan in _BACKFILL_PLAN)


def upgrade() -> None:
    for table, parent, fk_col, pk_col in _BACKFILL_PLAN:
        op.execute(
            f"""
            UPDATE {table} c
            SET tenant_id = p.tenant_id
            FROM {parent} p
            WHERE c.tenant_id IS NULL
              AND c.{fk_col} = p.{pk_col}
              AND p.tenant_id IS NOT NULL
            """
        )

    for table in _TABLES:
        op.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (SELECT id FROM tenants ORDER BY id LIMIT 1)
            WHERE tenant_id IS NULL
              AND (SELECT COUNT(*) FROM tenants) = 1
            """
        )

    for table in _TABLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF (SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL) > 0 THEN
                RAISE EXCEPTION
                  'Sprint 15q cohort 7: cannot promote {table}.tenant_id to NOT NULL — orphan rows remain. See docs/runbooks/r15k-tenant-orphan-backfill.md.';
              END IF;
            END $$
            """
        )

    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id DROP NOT NULL")
