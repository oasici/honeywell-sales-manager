"""V5 playbook expansion: steps + adherence + performance."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PlaybookStep(Base):
    """Materialised view of `playbooks.steps_json` blob, one row per step."""

    __tablename__ = "playbook_steps"
    __table_args__ = (UniqueConstraint("playbook_id", "step_no"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playbook_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playbooks.id", ondelete="CASCADE"), index=True
    )
    step_no: Mapped[int] = mapped_column(Integer, nullable=False)
    trigger_condition_json: Mapped[str] = mapped_column(Text, default="{}")
    recommended_action_json: Mapped[str] = mapped_column(Text, default="{}")
    expected_window_hours: Mapped[int] = mapped_column(Integer, default=48)
    success_metric: Mapped[str | None] = mapped_column(String(60), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class PlaybookAdherence(Base):
    __tablename__ = "playbook_adherence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    playbook_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playbooks.id", ondelete="CASCADE")
    )
    step_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playbook_steps.id", ondelete="CASCADE")
    )
    eligible_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")


class PlaybookPerformance(Base):
    __tablename__ = "playbook_performance"
    __table_args__ = (UniqueConstraint("playbook_id", "period_start", "period_end"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    playbook_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("playbooks.id", ondelete="CASCADE")
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    completion_rate: Mapped[float] = mapped_column(Float, default=0.0)
    won_rate: Mapped[float] = mapped_column(Float, default=0.0)
    lift_vs_control: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
