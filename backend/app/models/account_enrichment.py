"""Cached account-level rollups (Sprint 3 — Account Intelligence)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.customer import Customer


class AccountEnrichment(Base):
    """Per-customer cached aggregates; refreshed by AccountAggregateService."""

    __tablename__ = "account_enrichments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # R7-DB-1 — UNIQUE auto-creates a btree index.
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    # Round-15 Sprint 15j cohort 10 — defense-in-depth tenant scoping
    # (backfilled from parent customer).
    # Round-15 Sprint 15n cohort 4 — promoted to NOT NULL.
    # customer_id is NOT NULL on this row and ``customers.tenant_id``
    # is NOT NULL since Sprint 15k cohort 1; clean FK chain.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Round-11 R11-DB-CCY — currency Float→NUMERIC(19, 2).
    pipeline_open_amount: Mapped[float] = mapped_column(Numeric(19, 2, asdecimal=False), default=0.0)
    closed_won_revenue: Mapped[float] = mapped_column(Numeric(19, 2, asdecimal=False), default=0.0)
    active_deal_count: Mapped[int] = mapped_column(Integer, default=0)
    won_deal_count: Mapped[int] = mapped_column(Integer, default=0)
    lost_deal_count: Mapped[int] = mapped_column(Integer, default=0)
    total_deal_count: Mapped[int] = mapped_column(Integer, default=0)
    risk_index: Mapped[float] = mapped_column(Float, default=0.0)  # 0–100, higher = worse
    engagement_score: Mapped[float] = mapped_column(Float, default=0.0)  # 0–100
    last_touch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Round-10 R10-DB-6 — canonical audit timestamps. The enrichment row
    # used to rely on ``computed_at`` for staleness checks, but services
    # that didn't know about that field had no creation timestamp to
    # rely on. Defaults to NOW() so the column never has to be NULL.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    customer: Mapped["Customer"] = relationship("Customer", back_populates="account_enrichment", lazy="selectin")
