"""Configurable lead scoring factors — admin-managed weights and activation."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LeadScoringConfig(Base):
    """Stores per-factor scoring configuration for lead scoring."""

    __tablename__ = "lead_scoring_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # R7-DB-1 — UNIQUE auto-creates a btree index.
    factor_name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False,
    )
    weight: Mapped[int] = mapped_column(Integer, default=10)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
