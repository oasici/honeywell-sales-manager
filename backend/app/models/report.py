"""Self-service report template model."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReportTemplate(Base):
    __tablename__ = "report_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    entity_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # quote, opportunity, customer, email
    columns_json: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of column names
    filters_json: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON array: [{field, operator, value}]
    group_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[str] = mapped_column(String(4), default="desc")
    chart_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # bar, line, pie, table
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False)

    # Folder
    folder_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("report_folders.id"), nullable=True
    )

    # Scheduled email delivery
    email_schedule: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # weekly, daily, monthly, or None
    email_recipients: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON array of email addresses

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
