"""V5 foundation models.

Note: ``AccountFeaturesDaily`` and ``RepFeaturesDaily`` already live in
``app/models/feature_store_daily.py`` (with a smaller column set from
V4). The V5 expansion adds new columns there in-place — see that module
and the ``20260427_v5_foundation`` migration.

This file owns the only V5-foundation table that didn't exist before:
``contacts``.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Contact(Base):
    """Buyer-side individual; multiple contacts hang off one customer.

    Existing ``customers`` rows continue to act as the company anchor;
    downstream code may treat ``customer.email`` as a fallback contact
    when no row exists here yet. ``seniority_score`` is a 0..100 heuristic
    derived from title keywords on insert.
    """

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    department: Mapped[str | None] = mapped_column(String(120), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(60), nullable=True)
    seniority_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    is_decision_maker: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    linkedin_url: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
