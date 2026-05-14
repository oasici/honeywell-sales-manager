"""V5 timing engine model."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RecommendedActionWindow(Base):
    """V5 timing-based recommended action window for an opportunity.

    Round-15 F-002 / Sprint 15j cohort 4 — ``tenant_id`` added for
    defense in depth. Backfilled from ``opportunities.tenant_id`` by
    ``20260525_phase12_tenant_did_cohort4``.
    """

    __tablename__ = "recommended_action_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(60), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recommended_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    expected_uplift: Mapped[float | None] = mapped_column(Float, nullable=True)
    urgency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason_codes_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
