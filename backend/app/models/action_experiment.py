"""A/B testing for AI-generated actions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ActionExperiment(Base):
    __tablename__ = "action_experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
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
