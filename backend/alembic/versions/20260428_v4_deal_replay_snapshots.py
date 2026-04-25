"""v4 deal replay snapshots (additive learning layer)

Revision ID: 20260428_v4_deal_replay_snapshots
Revises: 20260427_v4_sales_events_shadow
Create Date: 2026-04-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260428_v4_deal_replay_snapshots"
down_revision = "20260427_v4_sales_events_shadow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v4_deal_replay_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("frames_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("meta_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("source_timeline_version", sa.String(length=64), nullable=False, server_default="v4-additive-readmodel"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_v4_deal_replay_opp_day",
        "v4_deal_replay_snapshots",
        ["opportunity_id", "snapshot_date"],
    )
    op.create_index(
        "ix_v4_deal_replay_opp_date",
        "v4_deal_replay_snapshots",
        ["opportunity_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_v4_deal_replay_opp_date", table_name="v4_deal_replay_snapshots")
    op.drop_constraint("uq_v4_deal_replay_opp_day", "v4_deal_replay_snapshots", type_="unique")
    op.drop_table("v4_deal_replay_snapshots")
