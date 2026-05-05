"""Invoice model — billing and payment tracking."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoice_customer", "customer_id"),
        Index("ix_invoice_status", "status"),
        # Round-4 R4-CLOSE-1 / R4-TEN-5 — tenant boundary on the
        # billing surface. Backfilled from customers.tenant_id by
        # alembic 20260504_billing_tenant.
        Index("ix_invoice_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    invoice_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    quote_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("quotes.id"), nullable=True)
    contract_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("contracts.id"), nullable=True)
    customer_id: Mapped[int] = mapped_column(Integer, ForeignKey("customers.id"), nullable=False)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    issue_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    # draft | sent | paid | overdue | voided
    currency: Mapped[str] = mapped_column(String(10), default="TRY")
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    tax_rate: Mapped[float] = mapped_column(Float, default=18.0)
    tax_amount: Mapped[float] = mapped_column(Float, default=0.0)
    grand_total: Mapped[float] = mapped_column(Float, default=0.0)
    items_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    customer = relationship("Customer", lazy="selectin")
    quote = relationship("Quote", lazy="selectin")
    contract = relationship("Contract", lazy="selectin")
    creator = relationship("User", lazy="selectin")
