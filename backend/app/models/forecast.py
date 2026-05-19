"""Forecast adjustment and pipeline snapshot models."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ForecastAdjustment(Base):
    """Manual manager adjustment to an opportunity's forecast amount or category.

    Round-15 F-002 / Sprint 15j — ``tenant_id`` added for defense in
    depth. Before, the tenant boundary was enforced *only* through the
    parent opportunity (Round-14 R14-AUTH-1 added the
    ``assert_same_tenant`` check at the service layer). With the
    column present, a future router that forgets the assert still
    can't cross tenants because ``scoped_for_user`` filters at the
    query layer. Backfilled from ``opportunities.tenant_id`` by
    ``20260522_phase12_tenant_defense_in_depth``.
    """

    __tablename__ = "forecast_adjustments"
    __table_args__ = (
        Index("ix_forecast_adj_opportunity", "opportunity_id"),
        Index("ix_forecast_adj_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-15 Sprint 15m cohort 3 — promoted to NOT NULL. The "one
    # deploy cycle" buffer the prior comment alluded to has elapsed
    # since 15j cohort 1 landed; backfill chain is clean.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False
    )
    adjusted_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # Round-10 R10-DB-CCY — adjustment deltas moved to NUMERIC(19, 2).
    original_amount: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), nullable=False
    )
    adjusted_amount: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), nullable=False
    )
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
    total_amount: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), nullable=False, default=0.0
    )
    weighted_amount: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), nullable=False, default=0.0
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
