"""Round-15 Sprint 15p cohort 6 — promote tenant_id NOT NULL on objections + workflow_rules.

Continues the cohort-1..5 NOT NULL campaign with two more tables:

  * ``objections``     — opportunity_id NOT NULL → opportunities.tenant_id
                          (NOT NULL since Sprint 15k cohort 1).
  * ``workflow_rules`` — created_by NOT NULL → users.tenant_id
                          (NOT NULL since R11).

Standard 4-step asyncpg-safe contract.

Revision ID: 20260609_phase13_tenant_not_null_cohort6
Revises: 20260608_phase13_tenant_not_null_cohort5
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op


revision = "20260609_phase13_tenant_not_null_cohort6"
down_revision = "20260608_phase13_tenant_not_null_cohort5"
branch_labels = None
depends_on = None


_BACKFILL_PLAN: tuple[tuple[str, str, str, str], ...] = (
    ("objections", "opportunities", "opportunity_id", "id"),
    ("workflow_rules", "users", "created_by", "id"),
)

_TABLES: tuple[str, ...] = tuple(plan[0] for plan in _BACKFILL_PLAN)


def upgrade() -> None:
    # Step 1 — defensive backfill.
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

    # Step 2 — single-tenant fallback.
    for table in _TABLES:
        op.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (SELECT id FROM tenants ORDER BY id LIMIT 1)
            WHERE tenant_id IS NULL
              AND (SELECT COUNT(*) FROM tenants) = 1
            """
        )

    # Step 3 — guard.
    for table in _TABLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF (SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL) > 0 THEN
                RAISE EXCEPTION
                  'Sprint 15p cohort 6: cannot promote {table}.tenant_id to NOT NULL — orphan rows remain. See docs/runbooks/r15k-tenant-orphan-backfill.md.';
              END IF;
            END $$
            """
        )

    # Step 4 — promote.
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id DROP NOT NULL")
