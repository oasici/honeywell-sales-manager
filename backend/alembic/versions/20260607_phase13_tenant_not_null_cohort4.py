"""Round-15 F-001 / Sprint 15n cohort 4 — promote tenant_id to NOT NULL on engagement add-ons.

Continues the cohort-1 (top-tier CRM), cohort-2 (billing + campaigns),
and cohort-3 (opportunity-derived) promotions. Cohort 4 targets six
"engagement add-on" tables with clean NOT NULL parent FKs into already-
NOT-NULL parents:

  * ``comments`` — user_id NOT NULL → users.tenant_id NOT NULL (R11).
  * ``shared_documents`` — created_by NOT NULL → users.tenant_id.
  * ``meeting_links`` — user_id NOT NULL → users.tenant_id.
  * ``webhook_subscriptions`` — created_by NOT NULL → users.tenant_id.
  * ``account_enrichments`` — customer_id NOT NULL → customers.tenant_id
    (NOT NULL since cohort 1).
  * ``v4_deal_replay_snapshots`` — opportunity_id NOT NULL →
    opportunities.tenant_id (NOT NULL since cohort 1).

Unlike cohorts 2/3 which shared a single parent table, each cohort-4
table needs a per-table backfill source. The migration declares the
mapping explicitly so future readers can audit it.

Same 4-step safety contract per asyncpg (one statement per
``op.execute()``):

  1. Defensive backfill from the declared parent table.
  2. Single-tenant fallback.
  3. Guard (``DO $$ … RAISE EXCEPTION``).
  4. ``ALTER COLUMN ... SET NOT NULL``.

Revision ID: 20260607_phase13_tenant_not_null_cohort4
Revises: 20260606_phase13_tenant_not_null_cohort3
Create Date: 2026-05-19
"""

from __future__ import annotations

from alembic import op


revision = "20260607_phase13_tenant_not_null_cohort4"
down_revision = "20260606_phase13_tenant_not_null_cohort3"
branch_labels = None
depends_on = None


# (table, parent_table, child_fk_column, parent_pk_column)
# Each parent_table.tenant_id is already NOT NULL as of cohort 1 (users
# since R11; customers / opportunities since Sprint 15k).
_BACKFILL_PLAN: tuple[tuple[str, str, str, str], ...] = (
    ("comments", "users", "user_id", "id"),
    ("shared_documents", "users", "created_by", "id"),
    ("meeting_links", "users", "user_id", "id"),
    ("webhook_subscriptions", "users", "created_by", "id"),
    ("account_enrichments", "customers", "customer_id", "id"),
    ("v4_deal_replay_snapshots", "opportunities", "opportunity_id", "id"),
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

    # Step 2 — single-tenant fallback (legacy Pre-V7 deployments).
    for table in _TABLES:
        op.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (SELECT id FROM tenants ORDER BY id LIMIT 1)
            WHERE tenant_id IS NULL
              AND (SELECT COUNT(*) FROM tenants) = 1
            """
        )

    # Step 3 — guard. Each table's check is its own DO block so a failure
    # message names the offending table.
    for table in _TABLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF (SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL) > 0 THEN
                RAISE EXCEPTION
                  'Sprint 15n cohort 4: cannot promote {table}.tenant_id to NOT NULL — orphan rows remain. See docs/runbooks/r15k-tenant-orphan-backfill.md.';
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
