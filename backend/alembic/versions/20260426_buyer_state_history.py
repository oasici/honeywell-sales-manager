"""buyer_state_history table

Revision ID: 20260426_buyer_state_history
Revises: 20260425_v4_momentum_fields
Create Date: 2026-04-26
"""

from alembic import op
from app.core.migration_helpers import create_table_if_absent
import sqlalchemy as sa


revision = "20260426_buyer_state_history"
down_revision = "20260425_v4_momentum_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table_if_absent(
        "buyer_state_history",
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("drivers_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("opportunity_id", "snapshot_date"),
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_buyer_state_snapshot_date ON buyer_state_history (snapshot_date)")


def downgrade() -> None:
    op.drop_index("ix_buyer_state_snapshot_date", table_name="buyer_state_history")
    op.drop_table("buyer_state_history")

