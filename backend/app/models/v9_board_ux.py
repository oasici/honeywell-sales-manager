"""V9 board UX models — WIP limits + pipeline review queue."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PipelineReviewQueueEntry(Base):
    __tablename__ = "pipeline_review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    suggested_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    suggested_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    suggested_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    suggestion_source: Mapped[str] = mapped_column(String(40), default="rule")
    evidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    __table_args__ = (
        Index("ix_pipeline_review_queue_decided_opp", "decided_at", "opportunity_id"),
    )
