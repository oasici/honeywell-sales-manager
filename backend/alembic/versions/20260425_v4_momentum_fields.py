"""opportunity_features_daily: add momentum band + drivers

Revision ID: 20260425_v4_momentum_fields
Revises: 20260425_activity_logs_source_ref
Create Date: 2026-04-25

Round-4 v1.9.14 — converted from ``op.batch_alter_table(...)`` to
raw SQL with IF NOT EXISTS guards so the migration is a no-op on
the bootstrapped schema.
"""

from alembic import op


revision = "20260425_v4_momentum_fields"
down_revision = "20260425_activity_logs_source_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE opportunity_features_daily "
        "ADD COLUMN IF NOT EXISTS momentum_band VARCHAR(20)"
    )
    op.execute(
        "ALTER TABLE opportunity_features_daily "
        "ADD COLUMN IF NOT EXISTS momentum_drivers_json TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE opportunity_features_daily "
        "DROP COLUMN IF EXISTS momentum_drivers_json"
    )
    op.execute(
        "ALTER TABLE opportunity_features_daily "
        "DROP COLUMN IF EXISTS momentum_band"
    )
