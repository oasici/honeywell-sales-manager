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
    # Round-15 Sprint 15j cohort 10 — defense-in-depth tenant scoping
    # (backfilled from parent customer; equally valid via user.tenant_id
    # since a pin requires both the user and the customer to live in
    # the same tenant).
    # Round-15 Sprint 15o cohort 5 — promoted to NOT NULL.
    # customer_id is NOT NULL and ``customers.tenant_id`` is NOT NULL
    # since Sprint 15k cohort 1.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # DB rows created before this feature may have NULL timestamps.
    pinned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=True
    )

    user = relationship("User", lazy="noload")
    customer = relationship("Customer", lazy="selectin")
