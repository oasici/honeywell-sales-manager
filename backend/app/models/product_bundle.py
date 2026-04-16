from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductBundle(Base):
    """Pre-configured product bundle for CPQ quoting."""
    __tablename__ = "product_bundles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    items_json: Mapped[str] = mapped_column(Text, nullable=False)  # [{spare_part_id, quantity}]
    bundle_price: Mapped[float | None] = mapped_column(Float, nullable=True)  # override price
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
