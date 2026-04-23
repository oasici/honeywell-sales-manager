"""Per-user pinned customers (Sprint 4 — prospecting list)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UserCustomerPin(Base):
    __tablename__ = "user_customer_pins"
    __table_args__ = (UniqueConstraint("user_id", "customer_id", name="uq_user_customer_pins_user_customer"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    # DB rows created before this feature may have NULL timestamps.
    pinned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=True
    )

    user = relationship("User", lazy="noload")
    customer = relationship("Customer", lazy="selectin")
