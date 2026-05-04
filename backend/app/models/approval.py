"""Multi-level approval routing models."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ApprovalRule(Base):
    """Configurable rule that triggers approval workflows based on entity thresholds."""

    __tablename__ = "approval_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 R4-TEN-12 — tenant_id added; backfilled by alembic
    # 20260504_add_tenant_id_to_engagement_billing (PHASE 4 follow-up).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), default="quote")
    condition_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # discount_pct, deal_amount, grand_total
    threshold_value: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_operator: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # gt, gte, lt, lte
    approver_role: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # role required to approve
    approver_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )  # specific user
    chain_mode: Mapped[str] = mapped_column(
        String(20), default="sequential",
    )  # sequential | parallel
    priority: Mapped[int] = mapped_column(
        Integer, default=0
    )  # higher = checked first
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Delegation: if approver is on PTO, delegate to this user
    delegate_to: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    delegate_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Escalation: auto-action when pending longer than escalation_hours
    escalation_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_action: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # auto_approve | escalate_to_manager

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    approver_user: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[approver_user_id], lazy="selectin"
    )


class ApprovalRequest(Base):
    """Single approval step within a multi-level approval chain."""

    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_entity", "entity_type", "entity_id"),
        Index("ix_approval_assigned_status", "assigned_to", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("approval_rules.id"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending, approved, rejected, skipped
    requested_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    assigned_to: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    decided_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    rule: Mapped["ApprovalRule"] = relationship(lazy="selectin")
    requester: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[requested_by], lazy="selectin"
    )
    assignee: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[assigned_to], lazy="selectin"
    )
    decider: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[decided_by], lazy="selectin"
    )
