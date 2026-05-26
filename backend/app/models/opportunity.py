"""Opportunity (deal/pipeline) model — v2 Sales Board foundation."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        Index("ix_opp_owner_stage", "owner_id", "stage"),
        Index("ix_opp_customer", "customer_id"),
        Index("ix_opp_close_date", "close_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    stage: Mapped[str] = mapped_column(String(30), nullable=False, default="prospecting")
    # Round-10 R10-DB-CCY — deal amount moved to NUMERIC(19, 2).
    amount: Mapped[float | None] = mapped_column(
        Numeric(19, 2, asdecimal=False), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(10), default="TRY")
    # F-012 (Round-19) — FX rate snapshot at create/update time.
    # Multi-currency forecast rolls up to ``tenant_settings.base_currency``
    # by multiplying ``amount * fx_rate_to_base``. NULL = legacy row
    # that predates this column; forecast falls back to 1.0 and flags
    # the result as estimate-tainted so finance can fix it.
    fx_rate_to_base: Mapped[float | None] = mapped_column(
        Numeric(18, 8, asdecimal=False), nullable=True
    )
    close_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | closed
    forecast_category: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # commit | best_case | pipeline | omitted
    # DB may contain NULL for legacy rows; keep nullable for production safety.
    probability: Mapped[float | None] = mapped_column(Float, default=0.0, nullable=True)
    loss_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Lead-source attribution. Migration 20260422_opportunity_foundation.py:33
    # creates the column; the model never declared it, so reads/writes
    # were silently no-op'd (audit DB-6).
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Revenue leak tracking — previous values before last update
    previous_stage: Mapped[str | None] = mapped_column(String(30), nullable=True)
    previous_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    previous_amount: Mapped[float | None] = mapped_column(
        Numeric(19, 2, asdecimal=False), nullable=True
    )

    pipeline_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("pipelines.id"), nullable=True, index=True
    )
    territory_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("territories.id"), nullable=True, index=True
    )

    # V8: multi-tenant boundary.
    # Round-15 Sprint 15k cohort 1 — promoted to NOT NULL. Backfill
    # sources, in order: customer.tenant_id → users.tenant_id via
    # owner_id (owner_id is NOT NULL on the row).
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    # F-017 Phase 7 — optimistic concurrency lock.
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # F-007 Phase 4 — soft-delete tombstones.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    delete_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    customer = relationship("Customer", lazy="selectin")
    # foreign_keys explicit because deleted_by also references users.id.
    owner = relationship("User", lazy="selectin", foreign_keys=[owner_id])
    events = relationship("OpportunityEvent", back_populates="opportunity", lazy="noload")
    # Explicit declaration so we can pair with `back_populates` on
    # OpportunitySignal (audit DB-4) — the previous `backref` worked
    # at runtime but was invisible to type-checkers and IDE jump-to.
    signals = relationship(
        "OpportunitySignal", back_populates="opportunity", lazy="noload",
    )
    quotes = relationship(
        "Quote",
        back_populates="opportunity",
        lazy="noload",
        foreign_keys="Quote.opportunity_id",
    )


class OpportunityEvent(Base):
    """Per-opportunity event log.

    Round-15 F-002 / Sprint 15j cohort 6 — ``tenant_id`` added for
    defense in depth. Backfilled from ``opportunities.tenant_id`` by
    ``20260527_phase12_tenant_did_cohort6``.
    """

    __tablename__ = "opportunity_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-15 Sprint 15m cohort 3 — promoted to NOT NULL.
    # opportunity_id is NOT NULL on this row and ``opportunities.tenant_id``
    # is NOT NULL post-cohort-1, so the FK chain is clean.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # email | quote | call | meeting | note | task | stage_change
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    opportunity = relationship("Opportunity", back_populates="events")


class OpportunitySignal(Base):
    """Risk/insight signals extracted from emails, quotes, or AI analysis."""
    __tablename__ = "opportunity_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-8 R8-PII-1 — tenant_id backfilled from opportunity.
    # Round-15 Sprint 15m cohort 3 — promoted to NOT NULL.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False, index=True
    )
    signal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # pricing_concern | competitor | no_touch | discount_risk | sla_breach | objection | positive
    severity: Mapped[str] = mapped_column(String(10), default="med")  # low | med | high
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)  # snippet + source
    source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)  # email | quote | ai
    source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_resolved: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    opportunity = relationship("Opportunity", back_populates="signals")


class Task(Base):
    """Next-best-action tasks for opportunities."""
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-8 R8-PII-1 — tenant_id backfilled from owner.tenant_id (or opportunity).
    # Sprint 16e cohort 9 — promoted NOT NULL via the same owner_id → users.tenant_id chain.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | done | dismissed
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual | rule | ai
    priority: Mapped[str] = mapped_column(String(10), default="normal")  # low | normal | high | urgent
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    owner = relationship("User", lazy="selectin")
    opportunity = relationship("Opportunity", lazy="selectin")
