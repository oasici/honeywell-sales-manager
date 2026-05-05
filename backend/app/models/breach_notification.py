"""Breach notification model for incident response workflow.

Round-5 R5-TEN-28: ``tenant_id`` added (alembic ``20260505_breach_folder_tenant``)
so a compliance officer in tenant A can no longer enumerate tenant B's
breach records or affected-customer counts.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BreachNotification(Base):
    __tablename__ = "breach_notifications"
    __table_args__ = (
        Index("ix_breach_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    breach_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    affected_customers_json: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # [customer_id, ...]
    severity: Mapped[str] = mapped_column(String(20), default="high")
    status: Mapped[str] = mapped_column(
        String(20), default="open"
    )  # open | investigating | notified | closed
    notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
