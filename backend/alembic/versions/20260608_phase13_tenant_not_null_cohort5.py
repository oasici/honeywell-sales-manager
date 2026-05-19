"""Round-15 Sprint 15o cohort 5 — promote tenant_id NOT NULL on user/opp/contract derivatives.

Continues the cohort-1/2/3/4 NOT NULL campaign. Cohort 5 covers 11
"second-tier" tables — all derived from a parent whose tenant_id is
already NOT NULL by this point in the chain (users, customers,
opportunities, contracts).

  * User-derived (users.tenant_id NOT NULL since R11):
      - ``coaching_plans``       — user_id NOT NULL
      - ``achievements``         — user_id NOT NULL
      - ``territories``          — created_by NOT NULL
      - ``report_folders``       — owner_id NOT NULL

  * Customer-derived (customers.tenant_id NOT NULL since cohort 1):
      - ``user_customer_pins``   — customer_id NOT NULL
      - ``account_teams``        — customer_id NOT NULL

  * Opportunity-derived (opportunities.tenant_id NOT NULL since cohort 1):
      - ``forecast_snapshot_details`` — opportunity_id NOT NULL
      - ``deal_replay_deltas``        — opportunity_id NOT NULL
      - ``opportunity_embeddings``    — opportunity_id NOT NULL
      - ``action_experiments``        — opportunity_id NOT NULL

  * Contract-derived (contracts.tenant_id NOT NULL since cohort 2):
      - ``revenue_schedules``    — contract_id NOT NULL

Per-table backfill plan declared explicitly so the FK source is
auditable for future readers. Same 4-step asyncpg-safe contract:

  1. Backfill from declared parent.
  2. Single-tenant fallback for legacy Pre-V7 deployments.
  3. DO-block guard (RAISE EXCEPTION if any orphan rows remain).
  4. ALTER COLUMN ... SET NOT NULL.

Revision ID: 20260608_phase13_tenant_not_null_cohort5
Revises: 20260607_phase13_tenant_not_null_cohort4
Create Date: 2026-05-19
"""

from __future__ import annotations

from alembic import op


revision = "20260608_phase13_tenant_not_null_cohort5"
down_revision = "20260607_phase13_tenant_not_null_cohort4"
branch_labels = None
depends_on = None


# (table, parent_table, child_fk_column, parent_pk_column)
_BACKFILL_PLAN: tuple[tuple[str, str, str, str], ...] = (
    # User-derived.
    ("coaching_plans", "users", "user_id", "id"),
    ("achievements", "users", "user_id", "id"),
    ("territories", "users", "created_by", "id"),
    ("report_folders", "users", "owner_id", "id"),
    # Customer-derived.
    ("user_customer_pins", "customers", "customer_id", "id"),
    ("account_teams", "customers", "customer_id", "id"),
    # Opportunity-derived.
    ("forecast_snapshot_details", "opportunities", "opportunity_id", "id"),
    ("deal_replay_deltas", "opportunities", "opportunity_id", "id"),
    ("opportunity_embeddings", "opportunities", "opportunity_id", "id"),
    ("action_experiments", "opportunities", "opportunity_id", "id"),
    # Contract-derived.
    ("revenue_schedules", "contracts", "contract_id", "id"),
)

_TABLES: tuple[str, ...] = tuple(plan[0] for plan in _BACKFILL_PLAN)


def upgrade() -> None:
    # Step 1 — defensive backfill from each table's declared parent.
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

    # Step 3 — guard. Per-table DO block so a failure names the table.
    for table in _TABLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF (SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL) > 0 THEN
                RAISE EXCEPTION
                  'Sprint 15o cohort 5: cannot promote {table}.tenant_id to NOT NULL — orphan rows remain. See docs/runbooks/r15k-tenant-orphan-backfill.md.';
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
