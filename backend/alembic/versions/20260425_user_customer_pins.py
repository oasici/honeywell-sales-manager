"""user_customer_pins — Sprint 4 pin/high-intent UI

Revision ID: 20260425_user_customer_pins
Revises: 20260424_account_enrichment
Create Date: 2026-04-25

"""

from alembic import op
import sqlalchemy as sa


revision = "20260425_user_customer_pins"
down_revision = "20260424_account_enrichment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_customer_pins",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("user_id", "customer_id", name="uq_user_customer_pins_user_customer"),
    )
    op.create_index("ix_user_customer_pins_user_id", "user_customer_pins", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_user_customer_pins_user_id", table_name="user_customer_pins")
    op.drop_table("user_customer_pins")
