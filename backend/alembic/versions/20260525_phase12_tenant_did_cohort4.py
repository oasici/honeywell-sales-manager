"""Round-15 F-002 / Sprint 15j cohort 4 — defense-in-depth tenant_id on V5 opportunity-derived tables.

Continues the cohort 1/2/3 pattern (forecast_adjustments, decision_gaps,
pipeline_review_queue). Each opportunity-derived table gets a nullable
``tenant_id`` column, backfilled from ``opportunities.tenant_id``, so
``scoped_for_user`` can enforce isolation at the query layer.

This revision covers:
  * ``objections`` — V5 objection records per opportunity.
  * ``recommended_action_windows`` — V5 timing windows per opportunity.
  * ``buyer_state_history`` — daily buyer-state classification per
    opportunity.

Same nullable-on-disk pattern: orphan rows (parent opportunity hard-
deleted before backfill) keep ``tenant_id`` NULL and remain invisible
to tenant-bound queries via SQL three-valued logic.

asyncpg constraint: each ``op.execute()`` carries exactly one
statement.

Revision ID: 20260525_phase12_tenant_did_cohort4
Revises: 20260524_phase12_tenant_did_cohort3
Create Date: 2026-05-14
"""

from __future__ import annotations

from alembic import op


revision = "20260525_phase12_tenant_did_cohort4"
down_revision = "20260524_phase12_tenant_did_cohort3"
branch_labels = None
depends_on = None


# (table_name, parent_join_column_on_table). Every entry pairs the
# child table with the FK column it uses to reach ``opportunities``.
_TABLES: list[tuple[str, str]] = [
    ("objections", "opportunity_id"),
    ("recommended_action_windows", "opportunity_id"),
    ("buyer_state_history", "opportunity_id"),
]


def upgrade() -> None:
    for table, fk_col in _TABLES:
        op.execute(
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS tenant_id INTEGER"
        )
        op.execute(
            f"""
            UPDATE {table} c
            SET tenant_id = o.tenant_id
            FROM opportunities o
            WHERE c.tenant_id IS NULL
              AND c.{fk_col} = o.id
              AND o.tenant_id IS NOT NULL
            """
        )
        op.execute(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_tenant_id "
            f"ON {table} (tenant_id)"
        )


def downgrade() -> None:
    for table, _ in _TABLES:
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_tenant_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS tenant_id")
