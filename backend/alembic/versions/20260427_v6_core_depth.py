"""V6 core depth: extend opportunity_features_daily with 3 columns

Revision ID: 20260427_v6_core_depth
Revises: 20260427_v5_similarity_repdna
Create Date: 2026-04-27

Adds three columns the V5 plan called for but V4 deferred:

* ``quote_revision_count_30d`` — explains stalling vs. progressing deals
* ``stage_velocity_days`` — days the deal sat in the current stage
* ``decision_maker_count`` — sharper than ``stakeholder_count`` for
  decision-gap detection

All DDL uses ``ADD COLUMN IF NOT EXISTS`` so the migration is safe to
re-run from any partial state.
"""

from alembic import op


revision = "20260427_v6_core_depth"
down_revision = "20260427_v5_similarity_repdna"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for ddl in (
        "ALTER TABLE opportunity_features_daily ADD COLUMN IF NOT EXISTS quote_revision_count_30d INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE opportunity_features_daily ADD COLUMN IF NOT EXISTS stage_velocity_days DOUBLE PRECISION",
        "ALTER TABLE opportunity_features_daily ADD COLUMN IF NOT EXISTS decision_maker_count INTEGER NOT NULL DEFAULT 0",
    ):
        op.execute(ddl)


def downgrade() -> None:
    for col in ("decision_maker_count", "stage_velocity_days", "quote_revision_count_30d"):
        op.execute(
            f"ALTER TABLE opportunity_features_daily DROP COLUMN IF EXISTS {col}"
        )
