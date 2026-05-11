from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StageConfig(Base):
    __tablename__ = "stage_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage_name: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    probability_pct: Mapped[float] = mapped_column(Float, default=0)
    rotting_threshold_days: Mapped[int] = mapped_column(Integer, default=7)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # V9: optional WIP limit per stage. NULL = no limit.
    wip_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Round-11 R11-DB-TS — pipeline stage configuration is admin-edited
    # and benefits from full audit history. Backfilled by alembic
    # 20260516_phase11_audit_timestamps.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
