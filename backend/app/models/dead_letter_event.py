"""Dead-letter event store (R4-EG-1).

Round-4 audit found that ``event_bus.publish()`` drops the payload
on the floor after retries exhaust — Sentry captures the exception
but no operator surface exists to inspect or replay. This model is
the persistence layer; the admin CRUD lives in
``app/api/v1/admin_dead_letters.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DeadLetterEvent(Base):
    __tablename__ = "dead_letter_events"
    __table_args__ = (
        Index("ix_dle_event_type", "event_type"),
        Index("ix_dle_handler_name", "handler_name"),
        Index("ix_dle_created_at", "created_at"),
        Index("ix_dle_replayed_at", "replayed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    handler_name: Mapped[str] = mapped_column(String(120), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    replayed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replayed_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
