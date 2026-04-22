"""Add ERP connector tables (v3 Sprint 1).

Revision ID: 20260422_add_erp_connector_tables
Revises: 20260413_add_customer_parent_id
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa


revision = "20260422_add_erp_connector_tables"
down_revision = "20260413_add_customer_parent_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "erp_connections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("endpoint", sa.String(length=500), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sync_cron", sa.String(length=64), nullable=True),
        sa.Column("last_customer_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_product_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_invoice_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_erp_connections_type", "erp_connections", ["type"])

    op.create_table(
        "erp_entity_mappings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("erp_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("internal_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_source", sa.String(length=8), nullable=False, server_default="erp"),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.UniqueConstraint(
            "connection_id", "entity_type", "internal_id",
            name="uq_erp_mapping_internal",
        ),
        sa.UniqueConstraint(
            "connection_id", "entity_type", "external_id",
            name="uq_erp_mapping_external",
        ),
    )
    op.create_index("ix_erp_mapping_conn", "erp_entity_mappings", ["connection_id"])
    op.create_index("ix_erp_mapping_entity", "erp_entity_mappings", ["entity_type"])
    op.create_index("ix_erp_mapping_internal", "erp_entity_mappings", ["internal_id"])
    op.create_index("ix_erp_mapping_external", "erp_entity_mappings", ["external_id"])

    op.create_table(
        "erp_sync_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("erp_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="delta"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("triggered_by", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("records_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_updated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("records_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cursor", sa.String(length=255), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_erp_sync_jobs_conn", "erp_sync_jobs", ["connection_id"])
    op.create_index("ix_erp_sync_jobs_entity", "erp_sync_jobs", ["entity"])
    op.create_index("ix_erp_sync_jobs_status", "erp_sync_jobs", ["status"])

    op.create_table(
        "erp_sync_conflicts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "connection_id",
            sa.Integer(),
            sa.ForeignKey("erp_connections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("internal_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(length=120), nullable=False),
        sa.Column("hss_snapshot", sa.Text(), nullable=False),
        sa.Column("erp_snapshot", sa.Text(), nullable=False),
        sa.Column("field_diffs", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column(
            "detected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
    )
    op.create_index("ix_erp_conflicts_conn", "erp_sync_conflicts", ["connection_id"])
    op.create_index("ix_erp_conflicts_entity", "erp_sync_conflicts", ["entity_type"])
    op.create_index("ix_erp_conflicts_internal", "erp_sync_conflicts", ["internal_id"])
    op.create_index("ix_erp_conflicts_status", "erp_sync_conflicts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_erp_conflicts_status", table_name="erp_sync_conflicts")
    op.drop_index("ix_erp_conflicts_internal", table_name="erp_sync_conflicts")
    op.drop_index("ix_erp_conflicts_entity", table_name="erp_sync_conflicts")
    op.drop_index("ix_erp_conflicts_conn", table_name="erp_sync_conflicts")
    op.drop_table("erp_sync_conflicts")

    op.drop_index("ix_erp_sync_jobs_status", table_name="erp_sync_jobs")
    op.drop_index("ix_erp_sync_jobs_entity", table_name="erp_sync_jobs")
    op.drop_index("ix_erp_sync_jobs_conn", table_name="erp_sync_jobs")
    op.drop_table("erp_sync_jobs")

    op.drop_index("ix_erp_mapping_external", table_name="erp_entity_mappings")
    op.drop_index("ix_erp_mapping_internal", table_name="erp_entity_mappings")
    op.drop_index("ix_erp_mapping_entity", table_name="erp_entity_mappings")
    op.drop_index("ix_erp_mapping_conn", table_name="erp_entity_mappings")
    op.drop_table("erp_entity_mappings")

    op.drop_index("ix_erp_connections_type", table_name="erp_connections")
    op.drop_table("erp_connections")
