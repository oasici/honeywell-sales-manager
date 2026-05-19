"""Round-15 F-001 / Sprint 15m cohort 3 — promote tenant_id to NOT NULL on opportunity-derived tables.

Continues the cohort-1 (top-tier CRM) and cohort-2 (billing + campaigns)
promotions. Cohort 3 targets the next tier — 4 opportunity-derived
tables where the parent FK is NOT NULL and ``opportunities.tenant_id``
is already NOT NULL from cohort 1:

  * ``opportunity_events`` — per-deal event log.
  * ``opportunity_signals`` — risk/insight signals.
  * ``decision_gaps`` — gap analysis output.
  * ``forecast_adjustments`` — per-deal commit overrides.

All four already carry ``tenant_id`` from Round-15 Sprint 15j (cohorts
6-9). The FK chain to ``opportunities`` is NOT NULL on the child side
and ``opportunities.tenant_id`` is NOT NULL on the parent side
post-cohort-1 — so the backfill is a no-op on a clean DB and the
guard fires only on genuinely-orphan rows.

Same 4-step safety contract per asyncpg (one statement per
``op.execute()``):

  1. Defensive backfill from ``opportunities.tenant_id`` via
     ``opportunity_id``.
  2. Single-tenant fallback.
  3. Guard.
  4. ``ALTER COLUMN ... SET NOT NULL``.

Revision ID: 20260606_phase13_tenant_not_null_cohort3
Revises: 20260605_phase13_tenant_not_null_cohort2
Create Date: 2026-05-18
"""

from __future__ import annotations

from alembic import op


revision = "20260606_phase13_tenant_not_null_cohort3"
down_revision = "20260605_phase13_tenant_not_null_cohort2"
branch_labels = None
depends_on = None


_TABLES: tuple[str, ...] = (
    "opportunity_events",
    "opportunity_signals",
    "decision_gaps",
    "forecast_adjustments",
)


def upgrade() -> None:
    # Step 1 — backfill from parent opportunity (NOT NULL FK).
    for table in _TABLES:
        op.execute(
            f"""
            UPDATE {table} c
            SET tenant_id = o.tenant_id
            FROM opportunities o
            WHERE c.tenant_id IS NULL
              AND c.opportunity_id = o.id
              AND o.tenant_id IS NOT NULL
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
                  'Sprint 15m cohort 3: cannot promote {table}.tenant_id to NOT NULL — orphan rows remain. See docs/runbooks/r15k-tenant-orphan-backfill.md.';
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
