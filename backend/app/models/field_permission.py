from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FieldPermission(Base):
    __tablename__ = "field_permissions"
    __table_args__ = (
        UniqueConstraint("role", "entity_type", "field_name", name="uq_role_entity_field"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    access_level: Mapped[str] = mapped_column(String(20), nullable=False, default="read")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
