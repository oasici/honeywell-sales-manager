"""Webhook subscription and delivery models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class WebhookSubscription(Base):
    """External webhook subscription for event notifications."""

    __tablename__ = "webhook_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 R4-TEN-10 — tenant_id added; backfilled by alembic
    # 20260504_phase4_tenant (PHASE 4 follow-up).
    # Round-15 Sprint 15n cohort 4 — promoted to NOT NULL.
    # created_by is NOT NULL on this row and ``users.tenant_id`` is
    # NOT NULL since R11; clean FK chain.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # noqa: E501 — sole index; no dup
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    event_types: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # JSON array of event type strings
    secret: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # HMAC-SHA256 signing secret
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    creator = relationship("User", lazy="selectin")
    deliveries = relationship(
        "WebhookDelivery",
        back_populates="subscription",
        lazy="noload",
        cascade="all, delete-orphan",
    )


class WebhookDelivery(Base):
    """Record of a single webhook delivery attempt."""

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        Index("ix_delivery_sub_delivered", "subscription_id", "delivered_at"),
        Index("ix_delivery_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 R4-TEN-10 — tenant_id added; backfilled by alembic
    # 20260504_phase4_tenant (PHASE 4 follow-up).
    # R5-DB-3 — explicit ix_delivery_tenant in __table_args__; the
    # implicit index from index=True duplicated it.
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subscription_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("webhook_subscriptions.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_body: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # truncated to 1000 chars
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    delivered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    subscription = relationship("WebhookSubscription", back_populates="deliveries")
