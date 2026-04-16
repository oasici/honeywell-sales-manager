"""Stage requirement model for guided selling — defines required fields per stage."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StageRequirement(Base):
    """Configurable per-stage requirements: required fields, validation rules, coaching tips."""

    __tablename__ = "stage_requirements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    # prospecting | qualified | proposal | negotiation | closed_won
    required_fields_json: Mapped[str] = mapped_column(Text, nullable=False)
    # e.g. ["amount","close_date","customer_id"]
    validation_rules_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # e.g. [{"rule":"has_quote","message":"En az 1 teklif gerekli"}]
    coaching_tips_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # e.g. ["Karar vericiyi tanimlayin","Butceyi dogrulayin"]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
