"""V9 NL search embedding tables — transcript + email."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TranscriptEmbedding(Base):
    __tablename__ = "transcript_embeddings"

    transcript_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("transcripts.id", ondelete="CASCADE"), primary_key=True
    )
    # Round-15 Sprint 15j cohort 13 — defense-in-depth tenant scoping
    # (backfilled from parent transcripts.tenant_id, itself populated
    # by the same cohort 13 migration).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    vocab_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class EmailEmbedding(Base):
    __tablename__ = "email_embeddings"

    email_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("email_requests.id", ondelete="CASCADE"), primary_key=True
    )
    # Round-15 Sprint 15j cohort 13 — defense-in-depth tenant scoping
    # (backfilled from parent email_requests.tenant_id).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    vocab_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
