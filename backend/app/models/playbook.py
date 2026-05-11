"""Playbook models — rule-based automation triggered by RevenueSignals."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Playbook(Base):
    """Round-10 R10-DB-3 — `tenant_id`, backfilled from
    ``users.tenant_id`` via ``created_by`` and promoted to NOT NULL by
    20260514_promote_phase9_not_null. Without this column, two
    tenants sharing an instance would see each other's automation rules.
    """

    __tablename__ = "playbooks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # JSON: [{"field": "signal_type", "op": "eq", "value": "no_touch"}, ...]
    # Supported operators: eq, neq, gte, lte, contains, in
    trigger_conditions_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    # JSON: [{"step": 1, "action_type": "task", "template": "Musteri ara", "delay_days": 0}, ...]
    steps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")

    category: Mapped[str] = mapped_column(String(50), default="general")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    creator = relationship("User", lazy="selectin")


class PlaybookExecution(Base):
    """Round-10 R10-DB-3 — `tenant_id` mirrored from parent playbook +
    opportunity (NOT NULL after 20260514_promote_phase9_not_null) so
    per-row scoping doesn't depend on a join.
    """

    __tablename__ = "playbook_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    playbook_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playbooks.id"), nullable=False, index=True
    )
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False, index=True
    )
    triggered_by_signal_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("revenue_signals.id"), nullable=True
    )

    current_step: Mapped[int] = mapped_column(Integer, default=1)

    # active | completed | cancelled | paused
    status: Mapped[str] = mapped_column(String(20), default="active")

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_action_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_exec_opp_playbook", "opportunity_id", "playbook_id"),
    )

    playbook = relationship("Playbook", lazy="selectin")
    opportunity = relationship("Opportunity", lazy="selectin")
    triggered_by_signal = relationship("RevenueSignal", lazy="noload")
