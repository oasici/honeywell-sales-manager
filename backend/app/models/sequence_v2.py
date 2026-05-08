"""Sequence V2 models — step run telemetry, domain events, stakeholders.

All tables are additive (non-breaking). Gated by FEATURE_SEQUENCES_V2 / FEATURE_BUYER_MAP.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SequenceStepRun(Base):
    """Telemetry record for each executed sequence step.

    One row per (enrollment_id, step_number) pair — used for idempotency
    checks and per-step analytics (duration, outcome, variant).
    """

    __tablename__ = "sequence_step_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    enrollment_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sequence_enrollments.id"), nullable=False, index=True
    )
    sequence_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sequences.id"), nullable=False, index=True
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_action: Mapped[str] = mapped_column(String(30), nullable=False)  # email | task | wait | branch
    variant_key: Mapped[str | None] = mapped_column(String(10), nullable=True)  # A | B | None
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="started"
    )  # started | completed | skipped | failed
    reason_codes: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    payload_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON step def at execution time
    # Some deployments backfill telemetry incrementally; allow NULLs for compatibility.
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("enrollment_id", "step_number", name="uq_step_run_enrollment_step"),
    )


class DomainEvent(Base):
    """Lightweight domain event log for audit and replay.

    Not a full event-sourcing store — a minimal audit buffer that captures
    who/what/when for each significant domain event. Kept for 90 days.
    """

    __tablename__ = "domain_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True, nullable=True
    )


class Stakeholder(Base):
    """Buying committee member on an opportunity or customer account.

    Powers the Buyer Relationship Map visualization. Gated by FEATURE_BUYER_MAP.
    """

    __tablename__ = "stakeholders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-8 R8-PII-1 — tenant_id backfilled from opportunity_id/customer_id chain.
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    seniority: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # executive | senior | mid_level | junior
    department_group: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # tech | finance | legal | operations | sales | marketing | hr | other
    buyer_role: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # decision_maker | influencer | champion | detractor | gatekeeper | end_user
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_auto_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=True
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )
