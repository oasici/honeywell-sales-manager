from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OpportunityFeaturesDaily(Base):
    """Daily per-opportunity feature snapshot.

    Round-15 F-002 / Sprint 15j cohort 5 — ``tenant_id`` added for
    defense in depth. Backfilled from ``opportunities.tenant_id`` by
    ``20260526_phase12_tenant_did_cohort5``.
    """

    __tablename__ = "opportunity_features_daily"

    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), primary_key=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Core recency / counts (MVP)
    deal_age_days: Mapped[int] = mapped_column(Integer, default=0)
    days_since_last_rep_touch: Mapped[int] = mapped_column(Integer, default=999)
    days_since_last_buyer_touch: Mapped[int] = mapped_column(Integer, default=999)
    rep_touch_count_14d: Mapped[int] = mapped_column(Integer, default=0)
    buyer_reply_count_14d: Mapped[int] = mapped_column(Integer, default=0)
    meeting_count_30d: Mapped[int] = mapped_column(Integer, default=0)

    # Quote + objections (MVP)
    quote_count: Mapped[int] = mapped_column(Integer, default=0)
    latest_discount_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    competitor_mentions_30d: Mapped[int] = mapped_column(Integer, default=0)
    pricing_objections_30d: Mapped[int] = mapped_column(Integer, default=0)

    positive_signal_count_14d: Mapped[int] = mapped_column(Integer, default=0)
    negative_signal_count_14d: Mapped[int] = mapped_column(Integer, default=0)

    # V4 placeholders to be filled in later sprints
    momentum_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    momentum_band: Mapped[str | None] = mapped_column(String(20), nullable=True)
    momentum_drivers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    buyer_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    close_probability: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── V6 core depth (see 20260427_v6_core_depth) ──
    quote_revision_count_30d: Mapped[int] = mapped_column(Integer, default=0)
    stage_velocity_days: Mapped[float | None] = mapped_column(Float, nullable=True)
    decision_maker_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_ofd_snapshot_date", "snapshot_date"),)


class AccountFeaturesDaily(Base):
    """Daily per-account rollup.

    Round-16 N15-DB-3 — ``tenant_id`` added for defense in depth.
    Backfilled from ``customers.tenant_id`` by
    ``20260614_add_tenant_id_to_feature_store_rollups``. Nullable until
    a follow-up cohort verifies the backfill in prod and promotes to
    NOT NULL.
    """

    __tablename__ = "account_features_daily"

    # MVP: account_id == customers.id (V1 mapping)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    open_opportunity_count: Mapped[int] = mapped_column(Integer, default=0)
    # Round-15 F-004 — promote to NUMERIC(19, 2) to match every other
    # currency column (R10-DB-CCY established the convention; this one
    # slipped past the original sweep).
    total_open_pipeline: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), default=0.0
    )
    avg_deal_health: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_touch_days: Mapped[int] = mapped_column(Integer, default=999)

    # ── V5 expansion (see 20260427_v5_foundation) ──
    avg_momentum: Mapped[float | None] = mapped_column(Float, nullable=True)
    stakeholder_coverage_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    buyer_engagement_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Migration declares NOT NULL with DEFAULT 0; add nullable=False
    # explicitly so SQLAlchemy autogenerate doesn't drift.
    objection_density_30d: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )
    expansion_signal_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_afd_snapshot_date", "snapshot_date"),)


class RepFeaturesDaily(Base):
    """Daily per-rep rollup.

    Round-16 N15-DB-3 — ``tenant_id`` added for defense in depth.
    Backfilled from ``users.tenant_id`` by
    ``20260614_add_tenant_id_to_feature_store_rollups``. Nullable until
    a follow-up cohort verifies the backfill in prod and promotes to
    NOT NULL.
    """

    __tablename__ = "rep_features_daily"

    rep_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), primary_key=True)
    snapshot_date: Mapped[date] = mapped_column(Date, primary_key=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    avg_followup_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    stakeholder_coverage_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    win_rate_adj: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── V5 expansion (see 20260427_v5_foundation) ──
    objection_recovery_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    sequence_adherence_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    stage_slippage_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    discount_dependence: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_deals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_rfd_snapshot_date", "snapshot_date"),)

