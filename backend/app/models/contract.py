from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Contract(Base):
    """Customer contract with lifecycle tracking."""

    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 R4-TEN-6 — tenant boundary on contracts. Backfilled
    # from customers.tenant_id by alembic 20260504_billing_tenant.
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    customer_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=False, index=True,
    )
    quote_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("quotes.id"), nullable=True, index=True,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    start_date = mapped_column(Date, nullable=True)
    end_date = mapped_column(Date, nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    terms_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    signed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    amendments = relationship(
        "ContractAmendment",
        back_populates="contract",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    # R5-RENDER-CONTRACT-1 — surface the customer summary on the
    # serialiser (mirroring the R5-API-1 invoice fix). selectin keeps
    # the list endpoint a single round-trip.
    customer = relationship("Customer", lazy="selectin")


class ContractAmendment(Base):
    """Amendment / change record for a contract."""

    __tablename__ = "contract_amendments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("contracts.id"), nullable=False, index=True,
    )
    amendment_type: Mapped[str] = mapped_column(String(50), nullable=False)
    changes_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_date = mapped_column(Date, nullable=True)
    approved_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
    )

    contract = relationship("Contract", back_populates="amendments")
