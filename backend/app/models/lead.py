"""Lead model — represents unqualified prospects before conversion to Customer."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # R7-DB-1 — UNIQUE auto-creates a btree index. Same R6-DB-1 family.
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(String(100), nullable=True)

    source: Mapped[str] = mapped_column(
        String(30), default="manual"
    )  # email, web, referral, manual, import

    status: Mapped[str] = mapped_column(
        String(20), default="new"
    )  # new, contacted, qualified, unqualified, converted

    lead_score: Mapped[int] = mapped_column(default=0)  # 0-100

    # V8: multi-tenant boundary.
    # Round-15 Sprint 15k cohort 1 — promoted to NOT NULL. Backfill
    # source: users.tenant_id via owner_id (NOT NULL FK).
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    # Conversion fields (populated when lead is converted)
    converted_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True
    )
    converted_opportunity_id: Mapped[int | None] = mapped_column(
        ForeignKey("opportunities.id"), nullable=True
    )
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    converted_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # F-007 Phase 4 — soft-delete tombstones.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    delete_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    owner: Mapped["User"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[owner_id], lazy="selectin"
    )

    __table_args__ = (
        Index("ix_lead_status", "status"),
        Index("ix_lead_owner", "owner_id"),
        Index("ix_lead_score", "lead_score"),
    )
