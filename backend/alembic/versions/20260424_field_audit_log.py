"""Field-level audit log (v3 Shield-equivalent retention).

Revision ID: 20260424_field_audit_log
Revises: 20260423_spare_part_stock_columns
Create Date: 2026-04-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260424_field_audit_log"
down_revision = "20260423_spare_part_stock_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "field_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("field_name", sa.String(length=96), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_kind", sa.String(length=16), nullable=False, server_default="user"),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_field_audit_entity", "field_audit_logs", ["entity_type", "entity_id"]
    )
    op.create_index(
        "ix_field_audit_changed_at", "field_audit_logs", ["changed_at"]
    )
    op.create_index("ix_field_audit_actor", "field_audit_logs", ["actor_id"])
    op.create_index("ix_field_audit_field", "field_audit_logs", ["field_name"])


def downgrade() -> None:
    op.drop_index("ix_field_audit_field", table_name="field_audit_logs")
    op.drop_index("ix_field_audit_actor", table_name="field_audit_logs")
    op.drop_index("ix_field_audit_changed_at", table_name="field_audit_logs")
    op.drop_index("ix_field_audit_entity", table_name="field_audit_logs")
    op.drop_table("field_audit_logs")
