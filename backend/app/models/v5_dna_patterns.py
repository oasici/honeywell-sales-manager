"""V5 segment-level DNA pattern + recommendation models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DnaPattern(Base):
    """Mined behavioural pattern at the segment level."""

    __tablename__ = "dna_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    pattern_name: Mapped[str] = mapped_column(String(200), nullable=False)
    pattern_type: Mapped[str] = mapped_column(String(40), nullable=False)
    sequence_template_json: Mapped[str] = mapped_column(Text, default="[]")
    support_count: Mapped[int] = mapped_column(Integer, default=0)
    win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    baseline_win_rate: Mapped[float] = mapped_column(Float, default=0.0)
    lift_vs_baseline: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)

    # ── V7 Bayesian uplift (see 20260427_v7_dna_uplift) ──
    smoothed_win_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    uplift_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    ci_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_promotable: Mapped[bool] = mapped_column(Boolean, default=False)

    last_trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class DnaRecommendation(Base):
    __tablename__ = "dna_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    segment_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    stage_scope: Mapped[str | None] = mapped_column(String(40), nullable=True)
    recommendation_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_pattern_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("dna_patterns.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
