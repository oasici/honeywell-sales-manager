"""Competitive intelligence — competitor mentions detected in emails/transcripts."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompetitorMention(Base):
    __tablename__ = "competitor_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-8 R8-PII-1 — tenant_id backfilled from opportunity_id chain.
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
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
    )  # keyword | ai | manual
    # ^ N15-DB F-01 (Round-15) — CHECK at
    # ``alembic/versions/20260610_phase14_enum_check_constraints.py:46-48``
    # allows ``manual`` too. Pre-fix the comment said only ``keyword | ai``
    # which contradicted the DB and would surprise a future contributor
    # who tried to add an admin-side "Manual mention" affordance.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
