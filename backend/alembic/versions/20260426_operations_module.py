"""Operations module: warehouses, stock levels, stock movements, BOM (v3).

Revision ID: 20260426_operations_module
Revises: 20260425_whatsapp_messages
Create Date: 2026-04-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260426_operations_module"
down_revision = "20260425_whatsapp_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=32), nullable=False, unique=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_warehouses_code", "warehouses", ["code"])

    op.create_table(
        "stock_levels",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "spare_part_id",
            sa.Integer(),
            sa.ForeignKey("spare_parts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            sa.Integer(),
            sa.ForeignKey("warehouses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("qty", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reserved_qty", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reorder_point", sa.Float(), nullable=True),
        sa.Column("last_counted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "spare_part_id", "warehouse_id", name="uq_stock_level_part_warehouse"
        ),
    )
    op.create_index("ix_stock_levels_part", "stock_levels", ["spare_part_id"])
    op.create_index("ix_stock_levels_warehouse", "stock_levels", ["warehouse_id"])

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "spare_part_id",
            sa.Integer(),
            sa.ForeignKey("spare_parts.id"),
            nullable=False,
        ),
        sa.Column(
            "warehouse_id",
            sa.Integer(),
            sa.ForeignKey("warehouses.id"),
            nullable=False,
        ),
        sa.Column("movement_type", sa.String(length=16), nullable=False),
        sa.Column("qty_delta", sa.Float(), nullable=False),
        sa.Column("qty_after", sa.Float(), nullable=False),
        sa.Column("unit_cost", sa.Float(), nullable=True),
        sa.Column("reference_type", sa.String(length=32), nullable=True),
        sa.Column("reference_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "actor_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_stock_movements_part", "stock_movements", ["spare_part_id"])
    op.create_index("ix_stock_movements_warehouse", "stock_movements", ["warehouse_id"])
    op.create_index("ix_stock_movements_type", "stock_movements", ["movement_type"])
    op.create_index("ix_stock_movements_created_at", "stock_movements", ["created_at"])

    op.create_table(
        "bills_of_materials",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "parent_spare_part_id",
            sa.Integer(),
            sa.ForeignKey("spare_parts.id"),
            nullable=False,
        ),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="v1"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "parent_spare_part_id", "version", name="uq_bom_parent_version"
        ),
    )
    op.create_index("ix_boms_parent", "bills_of_materials", ["parent_spare_part_id"])

    op.create_table(
        "bom_components",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "bom_id",
            sa.Integer(),
            sa.ForeignKey("bills_of_materials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "component_spare_part_id",
            sa.Integer(),
            sa.ForeignKey("spare_parts.id"),
            nullable=False,
        ),
        sa.Column("qty_per_parent", sa.Float(), nullable=False, server_default="1"),
        sa.Column("unit", sa.String(length=16), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index("ix_bom_components_bom", "bom_components", ["bom_id"])


def downgrade() -> None:
    op.drop_index("ix_bom_components_bom", table_name="bom_components")
    op.drop_table("bom_components")
    op.drop_index("ix_boms_parent", table_name="bills_of_materials")
    op.drop_table("bills_of_materials")
    op.drop_index("ix_stock_movements_created_at", table_name="stock_movements")
    op.drop_index("ix_stock_movements_type", table_name="stock_movements")
    op.drop_index("ix_stock_movements_warehouse", table_name="stock_movements")
    op.drop_index("ix_stock_movements_part", table_name="stock_movements")
    op.drop_table("stock_movements")
    op.drop_index("ix_stock_levels_warehouse", table_name="stock_levels")
    op.drop_index("ix_stock_levels_part", table_name="stock_levels")
    op.drop_table("stock_levels")
    op.drop_index("ix_warehouses_code", table_name="warehouses")
    op.drop_table("warehouses")
