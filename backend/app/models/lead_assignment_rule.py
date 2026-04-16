"""Lead assignment rules — automatic lead routing based on criteria."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LeadAssignmentRule(Base):
    __tablename__ = "lead_assignment_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    criteria_json: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # [{"field":"company","op":"contains","value":"sanayi"}]
    assign_to_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    assign_mode: Mapped[str] = mapped_column(
        String(20), default="specific_user"
    )  # round_robin | specific_user | least_loaded
    priority: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
