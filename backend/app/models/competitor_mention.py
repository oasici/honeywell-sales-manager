"""Competitive intelligence — competitor mentions detected in emails/transcripts."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompetitorMention(Base):
    __tablename__ = "competitor_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    competitor_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    source_entity_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # email | transcript
    source_entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=True, index=True
    )
    context_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # positive | neutral | negative
    detected_by: Mapped[str] = mapped_column(
        String(20), default="keyword"
    )  # keyword | ai
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
