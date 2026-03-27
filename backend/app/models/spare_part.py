from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SparePart(Base):
    __tablename__ = "spare_parts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    honeywell_code: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    name_en: Mapped[str | None] = mapped_column(String(500), nullable=True)
    name_tr: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    description_tr: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    subcategory: Mapped[str | None] = mapped_column(String(200), nullable=True)
    keywords_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    aliases_json: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON array
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    prices = relationship("PriceEntry", back_populates="spare_part", lazy="selectin")
