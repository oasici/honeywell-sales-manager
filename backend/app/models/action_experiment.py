"""A/B testing for AI-generated actions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ActionExperiment(Base):
    """A/B action experiment record on an opportunity.

    Round-15 F-002 / Sprint 15j cohort 6 — ``tenant_id`` added for
    defense in depth. Backfilled from ``opportunities.tenant_id`` by
    ``20260527_phase12_tenant_did_cohort6``.
    """

    __tablename__ = "action_experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-15 Sprint 15o cohort 5 — promoted to NOT NULL.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False, index=True
    )
    variant_a_json: Mapped[str] = mapped_column(Text, nullable=False)
    variant_b_json: Mapped[str] = mapped_column(Text, nullable=False)
    selected_variant: Mapped[str | None] = mapped_column(
        String(1), nullable=True
    )  # "a" | "b"
    outcome: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # won | lost | pending
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
