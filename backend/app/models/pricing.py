"""Advanced pricing models — tiered pricing and customer-specific contracts."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PriceTier(Base):
    __tablename__ = "price_tiers"
    __table_args__ = (
        Index("ix_pt_price_entry", "price_entry_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    price_entry_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("price_entries.id"), nullable=False
    )
    min_qty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    price_entry = relationship("PriceEntry", lazy="selectin")


class CustomerPricing(Base):
    __tablename__ = "customer_pricing"
    __table_args__ = (
        UniqueConstraint("customer_id", "spare_part_id", name="uq_customer_part_pricing"),
        Index("ix_cp_customer", "customer_id"),
        # Round-4 R4-TEN-15 — tenant boundary on negotiated customer prices.
        # TODO: backfill via customer_pricing → customers.tenant_id in alembic
        # 20260504_phase4_tenant.
        Index("ix_cp_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False)
    spare_part_id: Mapped[int] = mapped_column(Integer, ForeignKey("spare_parts.id"), nullable=False)
    contracted_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="TRY")
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    customer = relationship("Customer", lazy="selectin")
    spare_part = relationship("SparePart", lazy="selectin")
    creator = relationship("User", lazy="selectin")
