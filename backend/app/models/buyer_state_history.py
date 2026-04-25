from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BuyerStateHistory(Base):
    """Daily buyer-state classification per opportunity (V4-on-V1).

    Immutable per (opportunity_id, snapshot_date). Rebuilt nightly from feature store.
    """

    __tablename__ = "buyer_state_history"

    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), primary_key=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)

    state: Mapped[str] = mapped_column(String(30), nullable=False)  # e.g. exploring|evaluating|negotiating|stalling
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    drivers_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_buyer_state_snapshot_date", "snapshot_date"),)

