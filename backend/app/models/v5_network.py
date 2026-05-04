"""V5 network expansion: patterns + anomalies."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NetworkPattern(Base):
    __tablename__ = "network_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 v1.9.14 — column was added by migration but the
    # model file never declared it; schema_check caught the drift.
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    segment_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    pattern_type: Mapped[str] = mapped_column(String(40), nullable=False)
    pattern_json: Mapped[str] = mapped_column(Text, default="{}")
    performance_metric: Mapped[str] = mapped_column(String(40), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class NetworkAnomaly(Base):
    __tablename__ = "network_anomalies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 v1.9.14 — column was added by migration but the
    # model file never declared it; schema_check caught the drift.
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    segment_key: Mapped[str] = mapped_column(String(80), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(60), nullable=False)
    expected_value: Mapped[float] = mapped_column(Float, nullable=False)
    actual_value: Mapped[float] = mapped_column(Float, nullable=False)
    z_score: Mapped[float] = mapped_column(Float, nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="med")
    explanation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
