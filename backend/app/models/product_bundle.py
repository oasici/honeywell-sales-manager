from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductBundle(Base):
    """Pre-configured product bundle for CPQ quoting."""
    __tablename__ = "product_bundles"
    __table_args__ = (
        # Round-4 R4-TEN-15 — tenant boundary on CPQ bundle catalog.
        # TODO: backfill in alembic 20260504_phase4_tenant.
        Index("ix_pb_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    items_json: Mapped[str] = mapped_column(Text, nullable=False)  # [{spare_part_id, quantity}]
    # Round-11 R11-DB-CCY — currency Float→NUMERIC(19, 2). discount_pct
    # stays Float because it is a percentage, not money.
    bundle_price: Mapped[float | None] = mapped_column(Numeric(19, 2, asdecimal=False), nullable=True)
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
