"""Round-15 F-002 / Sprint 15j — defense-in-depth ``tenant_id`` on forecast_adjustments.

The Round-14 R14-AUTH-1 fix added a service-layer tenant check, but
``ForecastAdjustment`` has no ``tenant_id`` column of its own; the
boundary lives only on the parent ``Opportunity``. A future router
that forgets to call ``assert_same_tenant`` would re-open the gap.

Adding the column lets ``scoped_for_user(stmt, current_user,
column=ForecastAdjustment.tenant_id)`` enforce isolation at the query
layer too — the canonical pattern used everywhere else in the
codebase.

Backfill: copy from ``opportunities.tenant_id`` via the FK join.
Nullable on disk for one deploy cycle to absorb orphan rows
(opportunity hard-deleted before backfill). Follow-up revision will
promote NOT NULL after stable observation, matching the
20260518_phase12_tenant_columns → r13-orphan-tenant-backfill cadence.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement.

Revision ID: 20260522_r15_tenant_did1
Revises: 20260521_phase12_fk_indexes
Create Date: 2026-05-13

Note on the revision id length: revision strings are persisted into
``alembic_version.version_num``, which on legacy Postgres bootstraps
is VARCHAR(32). The previous full-length id
("20260522_phase12_tenant_defense_in_depth", 40 chars) exceeded the
column on environments where the env.py widener hadn't already
widened ``version_num`` to VARCHAR(128) — Render's prod hit that.
Shortened to ``20260522_r15_tenant_did1`` (23 chars) so the INSERT
succeeds regardless of widener state. Filename retained.
"""

from __future__ import annotations

from alembic import op


revision = "20260522_r15_tenant_did1"
down_revision = "20260521_phase12_fk_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── forecast_adjustments.tenant_id ──
    op.execute(
        "ALTER TABLE forecast_adjustments "
        "ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    # Backfill from parent opportunity. Orphan rows (opportunity deleted
    # before the adjustment row was migrated) keep tenant_id = NULL,
    # which the scoped() helper filters out for tenant users.
    op.execute(
        """
        UPDATE forecast_adjustments fa
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE fa.tenant_id IS NULL
          AND fa.opportunity_id = o.id
          AND o.tenant_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_forecast_adj_tenant "
        "ON forecast_adjustments (tenant_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_forecast_adj_tenant")
    op.execute(
        "ALTER TABLE forecast_adjustments DROP COLUMN IF EXISTS tenant_id"
    )
