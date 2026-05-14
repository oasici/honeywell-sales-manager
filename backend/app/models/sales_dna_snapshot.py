"""V4 Sales DNA: derived deal traits from feature store + activity + revenue_signals (read-only miner)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SalesDnaSnapshot(Base):
    """One row per (opportunity, UTC day); populated by miner — no CRM writer involvement."""

    __tablename__ = "v4_sales_dna_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(Integer, ForeignKey("opportunities.id"), nullable=False)
    # Round-15 Sprint 15j cohort 8 — defense-in-depth tenant scoping
    # (backfilled from parent opportunity).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    traits_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    meta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    miner_version: Mapped[str] = mapped_column(String(64), nullable=False, default="v4-sales-dna-mvp-1")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("opportunity_id", "snapshot_date", name="uq_v4_sales_dna_opp_day"),
        Index("ix_v4_sales_dna_opp_date", "opportunity_id", "snapshot_date"),
    )
