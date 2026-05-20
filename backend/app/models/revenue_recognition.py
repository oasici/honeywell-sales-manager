"""Revenue recognition models — schedule-based revenue tracking."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class RevenueSchedule(Base):
    __tablename__ = "revenue_schedules"
    __table_args__ = (
        Index("ix_rs_contract", "contract_id"),
        # Round-4 R4-TEN-8 — tenant boundary on revenue schedules.
        # Backfilled via contract → customer by alembic
        # 20260504_billing_tenant.
        Index("ix_rs_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-15 Sprint 15o cohort 5 — promoted to NOT NULL.
    # contract_id is NOT NULL and ``contracts.tenant_id`` is NOT NULL
    # since Sprint 15l cohort 2.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    contract_id: Mapped[int] = mapped_column(Integer, ForeignKey("contracts.id"), nullable=False)
    recognition_type: Mapped[str] = mapped_column(String(20), nullable=False, default="straight_line")
    # immediate | straight_line | milestone | usage
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # Round-10 R10-DB-CCY — schedule totals moved to NUMERIC(19, 2).
    total_amount: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), nullable=False
    )
    recognized_amount: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), default=0.0
    )
    currency: Mapped[str] = mapped_column(String(10), default="TRY")
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    contract = relationship("Contract", lazy="selectin")
    entries = relationship("RevenueScheduleEntry", back_populates="schedule", lazy="noload")
    creator = relationship("User", lazy="selectin")


class RevenueScheduleEntry(Base):
    __tablename__ = "revenue_schedule_entries"
    __table_args__ = (
        Index("ix_rse_schedule", "schedule_id"),
        # Same tenant boundary as parent schedule (R4-TEN-8).
        Index("ix_rse_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule_id: Mapped[int] = mapped_column(Integer, ForeignKey("revenue_schedules.id"), nullable=False)
    period: Mapped[str] = mapped_column(String(7), nullable=False)  # "2026-04" (YYYY-MM)
    amount: Mapped[float] = mapped_column(Numeric(19, 2, asdecimal=False), nullable=False)
    recognized_amount: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), default=0.0
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # N15-DB-1 (Round-15) — DB CHECK at
    # ``alembic/versions/20260610_phase14_enum_check_constraints.py:65-68``
    # enforces ``status IN ('pending','recognized','reversed')``. The
    # comment used to say ``adjusted`` which contradicted the CHECK and
    # would have caused a CheckViolation if any code path wrote it.
    # pending | recognized | reversed
    recognized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    schedule = relationship("RevenueSchedule", back_populates="entries", lazy="selectin")
