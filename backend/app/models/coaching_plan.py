"""Coaching plan models — structured improvement plans for sales reps."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CoachingPlan(Base):
    __tablename__ = "coaching_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    manager_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # Round-15 Sprint 15j cohort 10 — defense-in-depth tenant scoping
    # (backfilled from users.tenant_id via user_id).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # JSON: [{"indicator":"followup_adherence","target":75,"current":40}]
    goals_json: Mapped[str] = mapped_column(Text, nullable=False)
    weeks: Mapped[int] = mapped_column(Integer, default=4)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # active | completed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", foreign_keys=[user_id], lazy="selectin")
    manager = relationship("User", foreign_keys=[manager_id], lazy="selectin")
