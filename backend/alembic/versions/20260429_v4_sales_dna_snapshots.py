"""v4 sales DNA snapshots (read-only miner output)

Revision ID: 20260429_v4_sales_dna_snapshots
Revises: 20260428_v4_deal_replay_snapshots
Create Date: 2026-04-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260429_v4_sales_dna_snapshots"
down_revision = "20260428_v4_deal_replay_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "v4_sales_dna_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("traits_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("meta_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("miner_version", sa.String(length=64), nullable=False, server_default="v4-sales-dna-mvp-1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_v4_sales_dna_opp_day",
        "v4_sales_dna_snapshots",
        ["opportunity_id", "snapshot_date"],
    )
    op.create_index(
        "ix_v4_sales_dna_opp_date",
        "v4_sales_dna_snapshots",
        ["opportunity_id", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_v4_sales_dna_opp_date", table_name="v4_sales_dna_snapshots")
    op.drop_constraint("uq_v4_sales_dna_opp_day", "v4_sales_dna_snapshots", type_="unique")
    op.drop_table("v4_sales_dna_snapshots")
