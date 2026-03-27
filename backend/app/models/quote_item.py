from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class QuoteItem(Base):
    __tablename__ = "quote_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    spare_part_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("spare_parts.id"), nullable=True
    )
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    honeywell_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0)
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    line_total: Mapped[float] = mapped_column(Float, default=0.0)
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    quote = relationship("Quote", back_populates="items")
    spare_part = relationship("SparePart", lazy="selectin")
