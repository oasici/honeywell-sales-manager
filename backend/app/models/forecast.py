"""Forecast adjustment and pipeline snapshot models."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ForecastAdjustment(Base):
    """Manual manager adjustment to an opportunity's forecast amount or category."""

    __tablename__ = "forecast_adjustments"
    __table_args__ = (
        Index("ix_forecast_adj_opportunity", "opportunity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False
    )
    adjusted_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    original_amount: Mapped[float] = mapped_column(Float, nullable=False)
    adjusted_amount: Mapped[float] = mapped_column(Float, nullable=False)
    original_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    adjusted_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    opportunity: Mapped["Opportunity"] = relationship(lazy="selectin")  # type: ignore[name-defined]  # noqa: F821
    adjuster: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[adjusted_by], lazy="selectin"
    )


class PipelineSnapshot(Base):
    """Point-in-time snapshot of pipeline metrics grouped by stage."""

    __tablename__ = "pipeline_snapshots"
    __table_args__ = (
        Index("ix_pipeline_snapshot_date", "snapshot_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    opportunity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    weighted_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
