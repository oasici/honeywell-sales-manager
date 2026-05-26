from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class QuoteItem(Base):
    """Round-10 R10-DB-7 — canonical audit timestamps added. The parent
    ``quotes`` row has them, but per-line provenance was previously
    impossible to reconstruct (e.g. when an item is rolled into an
    existing quote). Defaults to NOW() so the column never has to be NULL.
    """

    __tablename__ = "quote_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quote_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Round-15 Sprint 15j cohort 9 — defense-in-depth tenant scoping
    # (backfilled from parent quote).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    spare_part_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("spare_parts.id"), nullable=True
    )
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    honeywell_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    # Round-10 R10-DB-CCY — unit_price + line_total moved to NUMERIC(19, 2).
    # discount_pct is a percentage; stays Float.
    unit_price: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), default=0.0
    )
    discount_pct: Mapped[float] = mapped_column(Float, default=0.0)
    line_total: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), default=0.0
    )
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_strategy: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    # F-027 (Phase 3) — pricing precedence source. Stamped by the
    # pricing resolver at line creation. ``ref`` carries the source
    # identifier (campaign_id / contract_id / tier name).
    price_source: Mapped[str] = mapped_column(
        String(40), nullable=False, default="catalog", server_default="catalog"
    )
    price_source_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    quote = relationship("Quote", back_populates="items")
    spare_part = relationship("SparePart", lazy="selectin")
