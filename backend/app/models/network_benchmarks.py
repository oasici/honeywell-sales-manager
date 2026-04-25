from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NetworkSegment(Base):
    """A lightweight segment definition for benchmarks.

    MVP: we auto-create stage-based segments like `stage:qualified`.
    Later: link to rule-based `segments` (customer grouping) if needed.
    """

    __tablename__ = "network_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    definition_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class SegmentBenchmarksDaily(Base):
    __tablename__ = "segment_benchmarks_daily"

    segment_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)

    # Core metrics
    win_rate_90d: Mapped[float | None] = mapped_column(Float, nullable=True)
    followup_median_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_discount_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_stakeholder_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    objection_rate_14d: Mapped[float | None] = mapped_column(Float, nullable=True)

    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_sbd_snapshot_date", "snapshot_date"),)

