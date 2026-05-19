from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StakeholderRole(Base):
    """Normalized stakeholder role assignment for decision-gap detection."""

    __tablename__ = "stakeholder_roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False, index=True
    )
    stakeholder_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stakeholders.id"), nullable=False, index=True
    )
    role_key: Mapped[str] = mapped_column(String(30), nullable=False)  # champion|economic|technical|procurement|legal
    confidence: Mapped[int] = mapped_column(Integer, default=0)  # store 0..100 to avoid float quirks
    source: Mapped[str] = mapped_column(String(20), default="rule")  # rule|manual|ai
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_stakeholder_roles_opp_role", "opportunity_id", "role_key"),
    )


class DecisionGap(Base):
    """Computed decision gaps for an opportunity.

    Round-15 F-002 / Sprint 15j cohort 2 — ``tenant_id`` added for
    defense in depth. Tenant boundary was previously enforced only
    via the parent opportunity FK; the column lets ``scoped_for_user``
    filter at the query layer too. Backfilled from
    ``opportunities.tenant_id`` by
    ``20260523_phase12_tenant_defense_in_depth_cohort2``.
    """

    __tablename__ = "decision_gaps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-15 Sprint 15m cohort 3 — promoted to NOT NULL.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False, index=True
    )
    gap_type: Mapped[str] = mapped_column(String(50), nullable=False)  # missing_economic_buyer|single_threaded_risk|...
    severity: Mapped[str] = mapped_column(String(10), default="med")  # low|med|high|critical
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    expected_roles_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    observed_roles_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_actions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    drivers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (Index("ix_decision_gaps_opp_type", "opportunity_id", "gap_type"),)

