"""Marketplace / plugin system models (v3).

Design rationale:
    - A **Plugin** is a published capability (metadata + manifest). We
      register first-party plugins at startup and let external ISVs add
      their own via ``/api/v1/marketplace/plugins`` (admin-only).
    - An **Installation** is a per-tenant binding of a plugin. Each
      installation owns its webhook endpoints, API key, and granted
      permission scopes. Removing the installation revokes everything.
    - **PluginEventSubscription** stores the webhook subscriptions
      created by the plugin - separated from core ``webhook_subscriptions``
      so uninstalling a plugin deletes its webhooks atomically.

For single-tenant deployments ``tenant_id`` defaults to 1; the field is
kept so the same table survives a future multi-tenant migration without
an ALTER.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Plugin(Base):
    __tablename__ = "plugins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    publisher: Mapped[str] = mapped_column(String(120), nullable=False, default="first_party")
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="1.0.0")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    homepage_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    icon_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # JSON array of scope strings: ["contacts:read","opportunities:write",...]
    scopes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # JSON array of event types the plugin can subscribe to.
    events_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    is_public: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PluginInstallation(Base):
    __tablename__ = "plugin_installations"
    __table_args__ = (
        UniqueConstraint("plugin_id", "tenant_id", name="uq_plugin_tenant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plugin_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plugins.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active"
    )  # active | suspended | uninstalled

    # JSON array of granted scopes (subset of Plugin.scopes_json).
    granted_scopes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # Per-installation opaque API token (Fernet-encrypted).
    api_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSON blob with tenant-specific configuration (webhook secrets, labels).
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    installed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    uninstalled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    plugin = relationship("Plugin", lazy="selectin")
    subscriptions = relationship(
        "PluginEventSubscription",
        back_populates="installation",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PluginEventSubscription(Base):
    __tablename__ = "plugin_event_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    installation_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("plugin_installations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_url: Mapped[str] = mapped_column(String(500), nullable=False)
    secret_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    installation = relationship("PluginInstallation", back_populates="subscriptions", lazy="noload")
