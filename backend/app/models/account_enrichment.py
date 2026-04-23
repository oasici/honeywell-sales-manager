"""Cached account-level rollups (Sprint 3 — Account Intelligence)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer


class AccountEnrichment(Base):
    """Per-customer cached aggregates; refreshed by AccountAggregateService."""

    __tablename__ = "account_enrichments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )

    pipeline_open_amount: Mapped[float] = mapped_column(Float, default=0.0)
    closed_won_revenue: Mapped[float] = mapped_column(Float, default=0.0)
    active_deal_count: Mapped[int] = mapped_column(Integer, default=0)
    won_deal_count: Mapped[int] = mapped_column(Integer, default=0)
    lost_deal_count: Mapped[int] = mapped_column(Integer, default=0)
    total_deal_count: Mapped[int] = mapped_column(Integer, default=0)
    risk_index: Mapped[float] = mapped_column(Float, default=0.0)  # 0–100, higher = worse
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0–100
    last_touch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    customer: Mapped["Customer"] = relationship("Customer", back_populates="account_enrichment", lazy="selectin")
