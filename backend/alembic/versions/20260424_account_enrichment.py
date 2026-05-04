"""account_enrichments — Sprint 3 Account Intelligence rollups

Revision ID: 20260424_account_enrichment
Revises: 20260423_email_opportunity
Create Date: 2026-04-24

"""

from alembic import op
from app.core.migration_helpers import create_table_if_absent
import sqlalchemy as sa


revision = "20260424_account_enrichment"
down_revision = "20260423_email_opportunity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    create_table_if_absent(
        "account_enrichments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("pipeline_open_amount", sa.Float(), nullable=False, server_default="0"),
        sa.Column("closed_won_revenue", sa.Float(), nullable=False, server_default="0"),
        sa.Column("active_deal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("won_deal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lost_deal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_deal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk_index", sa.Float(), nullable=False, server_default="0"),
        sa.Column("engagement_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("last_touch_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
    )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_account_enrichments_customer_id ON account_enrichments (customer_id)")


def downgrade() -> None:
    op.drop_index("ix_account_enrichments_customer_id", table_name="account_enrichments")
    op.drop_table("account_enrichments")
