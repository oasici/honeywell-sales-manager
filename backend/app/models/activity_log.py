"""Unified activity log for auto-captured and manual events."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Round-8 R8-PII-1 — tenant_id added; backfilled from
    # opportunity_id → opportunities.tenant_id (or customer_id → customers.tenant_id).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    activity_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # email_received, email_parsed, quote_created, quote_approved, quote_sent,
    #    task_created, task_completed, stage_change, note_added, transcript_uploaded
    entity_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # email, quote, opportunity, task, transcript, customer
    entity_id: Mapped[int] = mapped_column(nullable=False)

    opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id"), nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    summary: Mapped[str] = mapped_column(String(500), default="")
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(50), nullable=True)
    attendees_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    agenda: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Optional idempotency key for "same source event" dedupe across retries
    source_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships (lazy — only load when explicitly accessed)
    opportunity: Mapped["Opportunity"] = relationship(lazy="noload")  # type: ignore[name-defined]  # noqa: F821
    customer: Mapped["Customer"] = relationship(lazy="noload")  # type: ignore[name-defined]  # noqa: F821

    __table_args__ = (
        Index("ix_activity_log_entity", "entity_type", "entity_id"),
        Index("ix_activity_log_created", "created_at"),
    )
