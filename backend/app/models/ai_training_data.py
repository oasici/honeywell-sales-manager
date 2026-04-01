from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AITrainingData(Base):
    __tablename__ = "ai_training_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email_id: Mapped[int] = mapped_column(Integer, ForeignKey("email_requests.id"), nullable=False, index=True)
    original_parse: Mapped[str] = mapped_column(Text, nullable=False)
    corrected_parse: Mapped[str] = mapped_column(Text, nullable=False)
    correction_fields: Mapped[str] = mapped_column(String(255), nullable=False)
    model_used: Mapped[str] = mapped_column(String(20), default="claude")
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
