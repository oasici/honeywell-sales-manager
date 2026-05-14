"""Round-15 F-002 / Sprint 15j cohort 2 — tenant_id defense-in-depth on decision_gaps.

Cohort 2 extends the pattern established in
20260522_phase12_tenant_defense_in_depth: tables that inherit tenancy
through a parent FK get their own nullable ``tenant_id`` column,
backfilled from the parent. This lets ``scoped_for_user`` enforce
isolation at the query layer too, not just at the service layer's
``assert_same_tenant``.

This revision covers:
  * ``decision_gaps`` — joined to opportunities. Each gap row is
    tenant-scoped via opportunity_id.

Same nullable-on-disk pattern as cohort 1: orphan rows
(opportunity deleted before backfill) stay NULL and remain invisible
to tenant-bound queries via SQL three-valued logic.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement.

Revision ID: 20260523_phase12_tenant_defense_in_depth_cohort2
Revises: 20260522_phase12_tenant_defense_in_depth
Create Date: 2026-05-13

History note. f3dc3b2 briefly renamed this to
``20260523_r15_tenant_did2`` (23 chars), in response to a
suggested-fix message that turned out to be wrong: the long name
had already landed in ``alembic_version`` on Render (so the R11
widener was already keeping the column at VARCHAR(128)). After the
rename, alembic could not reconcile the stored long name with the
new short revision string and bailed with
``Can't locate revision identified by '<long-name>'``. Reverted
here.
"""

from __future__ import annotations

from alembic import op


revision = "20260523_phase12_tenant_defense_in_depth_cohort2"
down_revision = "20260522_phase12_tenant_defense_in_depth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── decision_gaps.tenant_id ──
    op.execute(
        "ALTER TABLE decision_gaps "
        "ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    op.execute(
        """
        UPDATE decision_gaps dg
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE dg.tenant_id IS NULL
          AND dg.opportunity_id = o.id
          AND o.tenant_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_decision_gaps_tenant_id "
        "ON decision_gaps (tenant_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_decision_gaps_tenant_id")
    op.execute(
        "ALTER TABLE decision_gaps DROP COLUMN IF EXISTS tenant_id"
    )
