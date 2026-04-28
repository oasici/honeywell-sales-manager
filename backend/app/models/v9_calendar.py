"""V9 calendar OAuth models — closes V2 Epic C1."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CalendarConnection(Base):
    __tablename__ = "calendar_connections"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_calendar_connections_user_provider"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)  # google | microsoft
    calendar_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    oauth_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class MeetingAutoLink(Base):
    __tablename__ = "meeting_auto_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_booking_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("meeting_bookings.id", ondelete="CASCADE"), nullable=True
    )
    external_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("opportunities.id", ondelete="SET NULL"), nullable=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    matched_by: Mapped[str] = mapped_column(String(40), default="attendee_email")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_meeting_auto_links_opp", "opportunity_id"),)
