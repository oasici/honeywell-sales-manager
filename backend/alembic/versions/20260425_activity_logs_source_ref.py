"""activity_logs: add source_ref for idempotency

Revision ID: 20260425_activity_logs_source_ref
Revises: 20260425_v4_feature_store_daily
Create Date: 2026-04-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260425_activity_logs_source_ref"
down_revision = "20260425_v4_feature_store_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("activity_logs") as batch:
        batch.add_column(sa.Column("source_ref", sa.String(length=120), nullable=True))
        batch.create_index("ix_activity_logs_source_ref", ["source_ref"])


def downgrade() -> None:
    with op.batch_alter_table("activity_logs") as batch:
        batch.drop_index("ix_activity_logs_source_ref")
        batch.drop_column("source_ref")

