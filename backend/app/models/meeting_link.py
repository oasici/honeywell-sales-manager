from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MeetingLink(Base):
    __tablename__ = "meeting_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    # R7-DB-1 — UNIQUE auto-creates a btree index.
    slug: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    availability_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    calendar_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
