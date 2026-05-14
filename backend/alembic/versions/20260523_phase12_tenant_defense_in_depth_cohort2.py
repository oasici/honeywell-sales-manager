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

Revision ID: 20260523_r15_tenant_did2
Revises: 20260522_r15_tenant_did1
Create Date: 2026-05-13

Note on the revision id length: revision strings are persisted into
``alembic_version.version_num``, which on legacy Postgres bootstraps
is VARCHAR(32). The previous full-length id
("20260523_phase12_tenant_defense_in_depth_cohort2", 48 chars) was
the trigger for this fix — the deploy explicitly raised
``StringDataRightTruncationError: value too long for type character
varying(32)``. Shortened to ``20260523_r15_tenant_did2`` (24 chars).
Filename retained.
"""

from __future__ import annotations

from alembic import op


revision = "20260523_r15_tenant_did2"
down_revision = "20260522_r15_tenant_did1"
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
