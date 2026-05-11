from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PriceEntry(Base):
    __tablename__ = "price_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spare_part_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("spare_parts.id"), nullable=False, index=True
    )
    # Round-11 R11-DB-CCY — currency Float→NUMERIC(19, 2). discount_pct
    # stays Float because it is a percentage, not money.
    list_price: Mapped[float] = mapped_column(Numeric(19, 2, asdecimal=False), nullable=False)
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    net_price: Mapped[float] = mapped_column(Numeric(19, 2, asdecimal=False), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    price_list_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    spare_part = relationship("SparePart", back_populates="prices", lazy="selectin")
