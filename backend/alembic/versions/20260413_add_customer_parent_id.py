"""add customer parent_id for account hierarchy

Revision ID: 20260413_add_customer_parent_id
Revises:
Create Date: 2026-04-13

"""
from alembic import op
import sqlalchemy as sa

revision = "20260413_add_customer_parent_id"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("parent_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_customers_parent_id", "customers", ["parent_id"])
    op.create_foreign_key(
        "fk_customers_parent_id",
        "customers",
        "customers",
        ["parent_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_customers_parent_id", "customers", type_="foreignkey")
    op.drop_index("ix_customers_parent_id", table_name="customers")
    op.drop_column("customers", "parent_id")
