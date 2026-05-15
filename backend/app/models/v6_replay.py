"""V6 deal replay deltas — pairwise OFD diff rows."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DealReplayDelta(Base):
    __tablename__ = "deal_replay_deltas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    # Round-15 Sprint 15j cohort 12 — defense-in-depth tenant scoping
    # (backfilled from parent opportunity).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    from_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    to_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    change_type: Mapped[str] = mapped_column(String(40), nullable=False)
    change_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    drivers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    counterfactual_hint: Mapped[str | None] = mapped_column(String(80), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_deal_replay_deltas_opp_to_ts", "opportunity_id", "to_ts"),
    )
