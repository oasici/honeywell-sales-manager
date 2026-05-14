"""V9 board UX models — WIP limits + pipeline review queue."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PipelineReviewQueueEntry(Base):
    """V9 board pipeline review queue.

    Round-15 F-002 / Sprint 15j cohort 3 — ``tenant_id`` added for
    defense in depth. Pre-fix the boundary lived only on the parent
    ``Opportunity`` FK; a router that forgot ``assert_same_tenant``
    could surface cross-tenant suggestions. Backfilled from
    ``opportunities.tenant_id`` by
    ``20260524_phase12_tenant_did_cohort3``.
    """

    __tablename__ = "pipeline_review_queue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    suggested_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    suggested_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Round-11 R11-DB-CCY — currency Float→NUMERIC(19, 2).
    suggested_amount: Mapped[float | None] = mapped_column(Numeric(19, 2, asdecimal=False), nullable=True)
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
