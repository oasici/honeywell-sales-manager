"""Custom field models — user-defined fields for entities."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CustomField(Base):
    __tablename__ = "custom_fields"
    __table_args__ = (
        UniqueConstraint("entity_type", "field_name", name="uq_custom_field_entity_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # customer|opportunity|quote|lead
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    field_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # text|number|date|select|checkbox
    options_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # for select type
    is_required: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    creator = relationship("User", lazy="selectin")


class CustomFieldValue(Base):
    __tablename__ = "custom_field_values"
    __table_args__ = (
        Index("ix_custom_field_value_entity", "entity_type", "entity_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    custom_field_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("custom_fields.id"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_number: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Calendar date — the timezone-aware DateTime variant caused
    # off-by-one display in non-UTC zones (audit DB-5, migration
    # 20260502_value_date_to_date).
    value_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    field = relationship("CustomField", lazy="selectin")
