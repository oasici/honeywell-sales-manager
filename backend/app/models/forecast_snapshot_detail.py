"""Per-opportunity snapshot captured alongside pipeline snapshots."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ForecastSnapshotDetail(Base):
    """Point-in-time capture of an individual opportunity's forecast state.

    Round-15 F-002 / Sprint 15j cohort 5 — ``tenant_id`` added for
    defense in depth. Backfilled from ``opportunities.tenant_id`` by
    ``20260526_phase12_tenant_did_cohort5``.
    """

    __tablename__ = "forecast_snapshot_details"
    __table_args__ = (
        Index("ix_fsd_snapshot", "snapshot_id"),
        Index("ix_fsd_opportunity", "opportunity_id"),
        Index("ix_fsd_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-15 Sprint 15o cohort 5 — promoted to NOT NULL.
    # opportunity_id is NOT NULL and ``opportunities.tenant_id`` is NOT NULL.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pipeline_snapshots.id"), nullable=True,
    )
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False,
    )
    forecast_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Round-11 R11-DB-CCY — currency Float→NUMERIC(19, 2).
    amount: Mapped[float] = mapped_column(Numeric(19, 2, asdecimal=False), nullable=False, default=0.0)
    stage: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    opportunity: Mapped["Opportunity"] = relationship(lazy="noload")  # type: ignore[name-defined]  # noqa: F821
