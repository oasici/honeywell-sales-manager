"""Stock-aware spare parts for ERP sync (v3 Sprint 4).

Revision ID: 20260423_spare_part_stock_columns
Revises: 20260422_add_erp_connector_tables
Create Date: 2026-04-23
"""

from alembic import op
import sqlalchemy as sa


revision = "20260423_spare_part_stock_columns"
down_revision = "20260422_add_erp_connector_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "spare_parts",
        sa.Column("current_stock_qty", sa.Float(), nullable=True),
    )
    op.add_column(
        "spare_parts",
        sa.Column("low_stock_threshold", sa.Float(), nullable=True),
    )
    op.add_column(
        "spare_parts",
        sa.Column("last_stock_sync_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("spare_parts", "last_stock_sync_at")
    op.drop_column("spare_parts", "low_stock_threshold")
    op.drop_column("spare_parts", "current_stock_qty")
