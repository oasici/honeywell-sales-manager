"""V6 federated benchmark stub model — privacy-aware cross-tenant aggregates."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FederatedBenchmark(Base):
    __tablename__ = "federated_benchmarks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 v1.9.14 — column was added by migration but the
    # model file never declared it; schema_check caught the drift.
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    benchmark_key: Mapped[str] = mapped_column(String(120), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    metric_name: Mapped[str] = mapped_column(String(60), nullable=False)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_bucket: Mapped[str | None] = mapped_column(String(40), nullable=True)
    privacy_level: Mapped[str] = mapped_column(String(20), default="aggregate_k_anon")
    tenant_count: Mapped[int] = mapped_column(Integer, default=0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    suppressed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_federated_benchmarks_key_date", "benchmark_key", "snapshot_date"),
    )
