"""Per-opportunity snapshot captured alongside pipeline snapshots."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ForecastSnapshotDetail(Base):
    """Point-in-time capture of an individual opportunity's forecast state."""

    __tablename__ = "forecast_snapshot_details"
    __table_args__ = (
        Index("ix_fsd_snapshot", "snapshot_id"),
        Index("ix_fsd_opportunity", "opportunity_id"),
        Index("ix_fsd_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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
