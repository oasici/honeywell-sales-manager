"""E-Signature request model — document signing workflow."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class SignatureRequest(Base):
    __tablename__ = "signature_requests"
    __table_args__ = (
        Index("ix_sig_token", "token", unique=True),
        Index("ix_sig_document", "document_type", "document_id"),
        Index("ix_sig_tenant", "tenant_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Round-4 R4-TEN-9 — tenant_id added; backfilled by alembic
    # 20260504_add_tenant_id_to_engagement_billing (PHASE 4 follow-up).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    document_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # quote | contract | invoice
    document_id: Mapped[int] = mapped_column(Integer, nullable=False)
    signer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    signer_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # pending | viewed | signed | declined | expired
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32)
    )
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + timedelta(days=7),
    )
    signature_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_by: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    creator = relationship("User", lazy="selectin")
