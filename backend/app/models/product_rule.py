"""Product catalog rules — volume discounts, bundle suggestions, quantity constraints."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ProductRule(Base):
    __tablename__ = "product_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spare_part_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("spare_parts.id"), nullable=True, index=True
    )
    category: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )  # applies to parts in this category
    rule_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # volume_discount | bundle_suggest | min_quantity | max_discount
    condition_json: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # {"field":"quantity","op":"gte","value":100}
    action_json: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # {"type":"discount","value":5} or {"type":"suggest","product_id":42}
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
