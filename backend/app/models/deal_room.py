"""Deal Room / Buyer Collaboration model."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DealRoom(Base):
    __tablename__ = "deal_rooms"
    __table_args__ = (
        Index("ix_deal_room_opportunity", "opportunity_id"),
        Index("ix_deal_room_token", "external_token", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    external_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    shared_items_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    mutual_action_plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_buyer_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    opportunity = relationship("Opportunity", lazy="selectin")
    creator = relationship("User", lazy="selectin")
