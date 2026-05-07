from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # R7-DB-1 — UNIQUE auto-creates a btree index.
    quote_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True, index=True
    )
    email_request_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("email_requests.id"), nullable=True, index=True
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    approved_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )

    # Status: draft -> pending_approval -> approved -> sent -> accepted -> rejected -> expired
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    language: Mapped[str] = mapped_column(String(5), default="tr")
    currency: Mapped[str] = mapped_column(String(10), default="TRY")

    # Financials
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    discount_total: Mapped[float] = mapped_column(Float, default=0.0)
    tax_rate: Mapped[float] = mapped_column(Float, default=20.0)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0)
    grand_total: Mapped[float] = mapped_column(Float, default=0.0)

    valid_days: Mapped[int] = mapped_column(Integer, default=30)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # V8: multi-tenant boundary
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # V9: revision tree
    parent_quote_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("quotes.id"), nullable=True
    )
    revision_no: Mapped[int] = mapped_column(Integer, default=1)
    superseded_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("quotes.id"), nullable=True
    )
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Win/Loss tracking (Feature 3)
    close_reason: Mapped[str | None] = mapped_column(String(50), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # v2: Opportunity linkage (nullable — backward compatible)
    opportunity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=True, index=True
    )

    # Versioning
    version: Mapped[int] = mapped_column(Integer, default=1)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    customer = relationship("Customer", back_populates="quotes", lazy="selectin")
    items = relationship(
        "QuoteItem", back_populates="quote", lazy="selectin", cascade="all, delete-orphan"
    )
    opportunity = relationship(
        "Opportunity", back_populates="quotes", lazy="noload",
        foreign_keys=[opportunity_id],
    )
