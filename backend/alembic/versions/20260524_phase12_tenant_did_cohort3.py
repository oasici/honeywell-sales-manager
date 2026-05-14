"""Round-15 F-002 / Sprint 15j cohort 3 — defense-in-depth tenant_id on pipeline_review_queue.

Cohort 3 continues the cohort 1/2 pattern: opportunity-derived tables
get their own nullable ``tenant_id`` column, backfilled from
``opportunities.tenant_id``. ``scoped_for_user`` can now enforce
isolation at the query layer too, not just at the service layer's
``assert_same_tenant``.

This revision covers:
  * ``pipeline_review_queue`` — joined to opportunities. Each
    suggestion row is tenant-scoped via opportunity_id.

Same nullable-on-disk pattern as cohorts 1 and 2: orphan rows
(opportunity deleted before backfill — cascade should clean these up
but defensive code stays defensive) keep ``tenant_id`` NULL and
remain invisible to tenant-bound queries via SQL three-valued logic.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement.

Revision ID: 20260524_phase12_tenant_did_cohort3
Revises: 20260523_phase12_tenant_defense_in_depth_cohort2
Create Date: 2026-05-14
"""

from __future__ import annotations

from alembic import op


revision = "20260524_phase12_tenant_did_cohort3"
down_revision = "20260523_phase12_tenant_defense_in_depth_cohort2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE pipeline_review_queue "
        "ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
    )
    op.execute(
        """
        UPDATE pipeline_review_queue prq
        SET tenant_id = o.tenant_id
        FROM opportunities o
        WHERE prq.tenant_id IS NULL
          AND prq.opportunity_id = o.id
          AND o.tenant_id IS NOT NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_pipeline_review_queue_tenant_id "
        "ON pipeline_review_queue (tenant_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_pipeline_review_queue_tenant_id")
    op.execute(
        "ALTER TABLE pipeline_review_queue DROP COLUMN IF EXISTS tenant_id"
    )
