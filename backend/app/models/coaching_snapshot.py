"""Coaching snapshot — periodic score captures for trend analysis."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CoachingSnapshot(Base):
    __tablename__ = "coaching_snapshots"
    __table_args__ = (
        Index("ix_coaching_snapshot_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    # Round-15 Sprint 15j cohort 10 — defense-in-depth tenant scoping
    # (backfilled from users.tenant_id via user_id).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    indicators_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user = relationship("User", lazy="selectin")
