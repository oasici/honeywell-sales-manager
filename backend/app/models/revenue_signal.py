"""Canonical revenue signal — unified event stream for Revenue Cockpit.

Every CRM/Signal/Transaction event feeds into this single table.
The cockpit reads from here. Playbooks trigger from here. Coaching scores from here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# ── Signal type registry ──
# Keep this authoritative list in one place.
SIGNAL_TYPES = {
    # From existing OpportunitySignal
    "pricing_concern", "competitor", "no_touch", "discount_risk",
    "sla_breach", "objection", "positive",
    # Revenue Cockpit additions
    "cross_sell_opportunity", "upsell_detected", "churn_risk",
    "expansion_signal", "deal_risk", "quote_stalled",
    # Process events
    "email_parsed", "stage_change", "activity_gap",
    # Coaching / SOP
    "coaching_needed", "sop_deviation", "forecast_miss",
    # Playbook
    "playbook_triggered", "playbook_completed",
}

SEVERITY_LEVELS = ("low", "med", "high", "critical")


class RevenueSignal(Base):
    __tablename__ = "revenue_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    signal_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Source traceability
    source_entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Linkage (all indexed for cockpit queries)
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=True
    )
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True
    )
    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # Signal quality
    severity: Mapped[str] = mapped_column(String(10), default="med")
    confidence: Mapped[float] = mapped_column(Float, default=0.5)

    # Action recommendation (AI or rule-based)
    recommended_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Flexible payload
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Cascade prevention: depth counter (handlers ignore depth > 3)
    depth: Mapped[int] = mapped_column(Integer, default=0)

    # Idempotency: source event dedup key
    event_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)

    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_rs_opp_created", "opportunity_id", "created_at"),
        Index("ix_rs_type_severity", "signal_type", "severity"),
        Index("ix_rs_owner_created", "owner_id", "created_at"),
        Index("ix_rs_customer", "customer_id"),
    )
