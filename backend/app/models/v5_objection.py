"""V5 objection intelligence models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Objection(Base):
    """V5 objection record on an opportunity.

    Round-15 F-002 / Sprint 15j cohort 4 — ``tenant_id`` added for
    defense in depth. Backfilled from ``opportunities.tenant_id`` by
    ``20260525_phase12_tenant_did_cohort4``.
    """

    __tablename__ = "objections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    # Soft pointer — pre-V4 events live in activity_logs, not the
    # shadow table, so we don't FK this column.
    event_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    objection_type: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(10), default="med")
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ttr_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class ObjectionResolutionAction(Base):
    __tablename__ = "objection_resolution_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    objection_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("objections.id", ondelete="CASCADE"), index=True
    )
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    action_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class ObjectionPattern(Base):
    """Mined success pattern per (segment_key, objection_type)."""

    __tablename__ = "objection_patterns"
    __table_args__ = (UniqueConstraint("segment_key", "objection_type"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 v1.9.14 — column was added by migration but the
    # model file never declared it; schema_check caught the drift.
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    segment_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    objection_type: Mapped[str] = mapped_column(String(40), nullable=False)
    recommended_resolution_json: Mapped[str] = mapped_column(Text, default="[]")
    success_rate: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    last_trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
