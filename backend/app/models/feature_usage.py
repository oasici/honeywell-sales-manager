from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FeatureUsage(Base):
    __tablename__ = "feature_usage"
    __table_args__ = (
        Index("ix_feature_usage_name_created", "feature_name", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-8 R8-PII-1 — tenant_id backfilled from user.tenant_id.
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # Round-8 R8-FK-1 — proper FK so user deletion cascades cleanly.
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    feature_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
