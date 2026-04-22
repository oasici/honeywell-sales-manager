"""Marketplace / plugin system tables (v3).

Revision ID: 20260427_marketplace_plugins
Revises: 20260426_operations_module
Create Date: 2026-04-27
"""

from alembic import op
import sqlalchemy as sa


revision = "20260427_marketplace_plugins"
down_revision = "20260426_operations_module"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plugins",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("publisher", sa.String(length=120), nullable=False, server_default="first_party"),
        sa.Column("version", sa.String(length=32), nullable=False, server_default="1.0.0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("homepage_url", sa.String(length=500), nullable=True),
        sa.Column("icon_url", sa.String(length=500), nullable=True),
        sa.Column("scopes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("events_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_plugins_slug", "plugins", ["slug"])

    op.create_table(
        "plugin_installations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "plugin_id",
            sa.Integer(),
            sa.ForeignKey("plugins.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("granted_scopes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("api_token_encrypted", sa.Text(), nullable=True),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("installed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "installed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("uninstalled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("plugin_id", "tenant_id", name="uq_plugin_tenant"),
    )
    op.create_index("ix_plugin_installations_plugin", "plugin_installations", ["plugin_id"])
    op.create_index("ix_plugin_installations_tenant", "plugin_installations", ["tenant_id"])

    op.create_table(
        "plugin_event_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "installation_id",
            sa.Integer(),
            sa.ForeignKey("plugin_installations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("target_url", sa.String(length=500), nullable=False),
        sa.Column("secret_hash", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_plugin_event_subs_installation",
        "plugin_event_subscriptions",
        ["installation_id"],
    )
    op.create_index(
        "ix_plugin_event_subs_event", "plugin_event_subscriptions", ["event_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_plugin_event_subs_event", table_name="plugin_event_subscriptions")
    op.drop_index("ix_plugin_event_subs_installation", table_name="plugin_event_subscriptions")
    op.drop_table("plugin_event_subscriptions")
    op.drop_index("ix_plugin_installations_tenant", table_name="plugin_installations")
    op.drop_index("ix_plugin_installations_plugin", table_name="plugin_installations")
    op.drop_table("plugin_installations")
    op.drop_index("ix_plugins_slug", table_name="plugins")
    op.drop_table("plugins")
