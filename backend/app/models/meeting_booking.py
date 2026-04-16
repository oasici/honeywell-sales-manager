from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MeetingBooking(Base):
    __tablename__ = "meeting_bookings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_link_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("meeting_links.id"), nullable=False, index=True
    )
    booker_name: Mapped[str] = mapped_column(String(200), nullable=False)
    booker_email: Mapped[str] = mapped_column(String(255), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
