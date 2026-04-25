"""opportunity_features_daily: add momentum band + drivers

Revision ID: 20260425_v4_momentum_fields
Revises: 20260425_activity_logs_source_ref
Create Date: 2026-04-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260425_v4_momentum_fields"
down_revision = "20260425_activity_logs_source_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("opportunity_features_daily") as batch:
        batch.add_column(sa.Column("momentum_band", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("momentum_drivers_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("opportunity_features_daily") as batch:
        batch.drop_column("momentum_drivers_json")
        batch.drop_column("momentum_band")

