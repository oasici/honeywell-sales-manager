"""Round-15 Sprint 16e cohort 9 — promote tenant_id NOT NULL on the
remaining 8 child tables flagged by the Round-15 audit M-01 plan
(``docs/audits/2026-05-20-cross-layer-audit-round15.md`` §10).

Tables + parent FK chains (all parents are already NOT NULL):

  * ``achievements``              — user_id NOT NULL → users.tenant_id NOT NULL.
                                    Model already declares NOT NULL — this
                                    migration closes N15-DB-2 (model/db drift).
  * ``push_subscriptions``         — user_id NOT NULL → users.tenant_id NOT NULL.
  * ``tasks``                       — owner_id NOT NULL → users.tenant_id NOT NULL.
                                    ``opportunity_id`` is nullable, so owner_id
                                    is the safer backfill source.
  * ``stakeholders``                — opportunity_id / customer_id (both nullable);
                                    COALESCE backfill in two passes.
  * ``campaign_members``            — campaign_id NOT NULL → campaigns.tenant_id
                                    NOT NULL since cohort 2.
  * ``webhook_deliveries``          — subscription_id NOT NULL → webhook_subscriptions
                                    .tenant_id NOT NULL since cohort 4.
  * ``revenue_schedule_entries``    — schedule_id NOT NULL → revenue_schedules.tenant_id
                                    NOT NULL.
  * ``contract_amendments``         — contract_id NOT NULL → contracts.tenant_id
                                    NOT NULL since cohort 2.

Pattern matches cohort 7 / 8: backfill from parent → orphan check that
raises a clear migration error → ALTER COLUMN SET NOT NULL.

Round-15 audit risk assessment: LOW. Same shape as cohorts 1-8 which all
ran cleanly. Stakeholder COALESCE path is the only novel SQL — verified
against the existing rows where either FK column is null in dev.

**DBA-review note (Sprint 16e):** Before running on prod, follow the
runbook at ``docs/runbooks/r15k-tenant-orphan-backfill.md`` to verify
zero orphan rows in each child. The orphan_check DO block will refuse
to promote a column when the parent chain breaks down, so partial
production data won't silently break.

Revision ID: 20260613_phase13_tenant_not_null_cohort9
Revises: 20260612_phase13_tenant_not_null_cohort8
Create Date: 2026-05-20
"""

from __future__ import annotations

from alembic import op


revision = "20260613_phase13_tenant_not_null_cohort9"
down_revision = "20260612_phase13_tenant_not_null_cohort8"
branch_labels = None
depends_on = None


# Simple single-parent backfills — same pattern as cohort 7/8.
_BACKFILL_PLAN: tuple[tuple[str, str, str, str], ...] = (
    # (child_table, parent_table, child_fk_col, parent_pk_col)
    ("achievements", "users", "user_id", "id"),
    ("push_subscriptions", "users", "user_id", "id"),
    ("tasks", "users", "owner_id", "id"),
    ("campaign_members", "campaigns", "campaign_id", "id"),
    ("webhook_deliveries", "webhook_subscriptions", "subscription_id", "id"),
    ("revenue_schedule_entries", "revenue_schedules", "schedule_id", "id"),
    ("contract_amendments", "contracts", "contract_id", "id"),
)

_TABLES: tuple[str, ...] = tuple(plan[0] for plan in _BACKFILL_PLAN) + ("stakeholders",)


def upgrade() -> None:
    # ── 1. Backfill single-parent children from their parent's tenant_id ──
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

    # ── 2. Stakeholder two-pass backfill — opportunity first, then customer ──
    # Stakeholder rows attached to a (valid) opportunity inherit from it.
    op.execute(
        """
        UPDATE stakeholders s
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE s.tenant_id IS NULL
          AND s.opportunity_id IS NOT NULL
          AND s.opportunity_id = o.id
          AND o.tenant_id IS NOT NULL
        """
    )
    # Remaining stakeholders attached to a (valid) customer.
    op.execute(
        """
        UPDATE stakeholders s
        SET tenant_id = c.tenant_id
        FROM customers c
        WHERE s.tenant_id IS NULL
          AND s.customer_id IS NOT NULL
          AND s.customer_id = c.id
          AND c.tenant_id IS NOT NULL
        """
    )

    # ── 3. Single-tenant fallback (dev / single-tenant installs) ──
    for table in _TABLES:
        op.execute(
            f"""
            UPDATE {table}
            SET tenant_id = (SELECT id FROM tenants ORDER BY id LIMIT 1)
            WHERE tenant_id IS NULL
              AND (SELECT COUNT(*) FROM tenants) = 1
            """
        )

    # ── 4. Orphan check — raise a loud, actionable error if any row is
    # still NULL. Matches cohort-7's runbook reference so on-call has a
    # single place to look. ──
    for table in _TABLES:
        op.execute(
            f"""
            DO $$ BEGIN
              IF (SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL) > 0 THEN
                RAISE EXCEPTION
                  'Sprint 16e cohort 9: cannot promote {table}.tenant_id to NOT NULL — orphan rows remain. See docs/runbooks/r15k-tenant-orphan-backfill.md.';
              END IF;
            END $$
            """
        )

    # ── 5. Promote each column to NOT NULL ──
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id SET NOT NULL")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN tenant_id DROP NOT NULL")
