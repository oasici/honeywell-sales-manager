from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.account_enrichment import AccountEnrichment

from app.core.database import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    tax_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    preferred_lang: Mapped[str] = mapped_column(String(5), default="tr")
    created_by: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # KVKK Compliance fields
    kvkk_consent: Mapped[bool] = mapped_column(Boolean, default=False)
    kvkk_consent_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    kvkk_consent_method: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # email | form | verbal | import
    data_retention_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    data_processing_purpose: Mapped[str | None] = mapped_column(
        String(200), nullable=True
    )
    deletion_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Data classification
    data_classification: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # public|internal|confidential|restricted

    # Enrichment fields
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    annual_revenue: Mapped[str | None] = mapped_column(String(50), nullable=True)
    website: Mapped[str | None] = mapped_column(String(255), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    territory_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("territories.id"), nullable=True, index=True
    )

    # Account hierarchy
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("customers.id"), nullable=True, index=True
    )
    subsidiaries = relationship(
        "Customer", foreign_keys="Customer.parent_id", back_populates="parent_account", lazy="noload"
    )
    parent_account = relationship(
        "Customer", foreign_keys="Customer.parent_id", remote_side="Customer.id", lazy="selectin"
    )

    quotes = relationship("Quote", back_populates="customer", lazy="selectin")
    email_requests = relationship("EmailRequest", back_populates="customer", lazy="selectin")
    account_enrichment: Mapped["AccountEnrichment | None"] = relationship(
        "AccountEnrichment",
        back_populates="customer",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )
