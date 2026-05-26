from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Numeric, String, Text
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
    # Round-10 R10-DB-CCY — currency columns moved from Float (binary
    # IEEE 754) to NUMERIC(19, 2) (decimal). `asdecimal=False` keeps
    # the Python-side type as `float` so serializers + callers don't
    # change. NUMERIC eliminates the accumulating-rounding-error class
    # of bugs that hits revenue reconciliation as line items grow.
    # `tax_rate` is a percentage, not currency, so stays Float.
    subtotal: Mapped[float] = mapped_column(Numeric(19, 2, asdecimal=False), default=0.0)
    discount_total: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), default=0.0
    )
    tax_rate: Mapped[float] = mapped_column(Float, default=20.0)
    tax_amount: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), default=0.0
    )
    grand_total: Mapped[float] = mapped_column(
        Numeric(19, 2, asdecimal=False), default=0.0
    )

    valid_days: Mapped[int] = mapped_column(Integer, default=30)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # V8: multi-tenant boundary.
    # Round-15 Sprint 15k cohort 1 — promoted to NOT NULL. Backfill
    # chain: opportunity.tenant_id → customer.tenant_id →
    # users.tenant_id via created_by.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
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
    # ``version``     — *semantic* version (v1 sent → customer rejects →
    #                   rep edits → v2 supersedes v1). See F-026.
    # ``row_version`` — *optimistic concurrency* counter (F-017).
    #                   Every UPDATE bumps it; conflicting concurrent
    #                   edits race on this and the loser gets 409.
    version: Mapped[int] = mapped_column(Integer, default=1)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # F-026 (Phase 3) — supersede chain. When rep edits a sent quote
    # to create v2, the v1 row's superseded_by_id points at v2.
    superseded_by_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("quotes.id"), nullable=True
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # F-007 Phase 4 — soft-delete tombstones.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    delete_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)

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
