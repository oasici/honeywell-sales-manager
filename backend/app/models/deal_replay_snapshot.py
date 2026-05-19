"""V4 deal replay: immutable-ish daily snapshot of normalized timeline (+ optional feature row pointer)."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DealReplaySnapshot(Base):
    """Derived-only storage: built from additive timeline projection (no CRM writer changes)."""

    __tablename__ = "v4_deal_replay_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(Integer, ForeignKey("opportunities.id"), nullable=False)
    # Round-15 Sprint 15j cohort 8 — defense-in-depth tenant scoping
    # (backfilled from parent opportunity).
    # Round-15 Sprint 15n cohort 4 — promoted to NOT NULL.
    # opportunity_id is NOT NULL on this row and
    # ``opportunities.tenant_id`` is NOT NULL since Sprint 15k cohort 1.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)

    frames_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    meta_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    source_timeline_version: Mapped[str] = mapped_column(
        String(64), nullable=False, default="v4-additive-readmodel"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("opportunity_id", "snapshot_date", name="uq_v4_deal_replay_opp_day"),
        Index("ix_v4_deal_replay_opp_date", "opportunity_id", "snapshot_date"),
    )
