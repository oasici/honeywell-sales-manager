"""V8 sequence text embedding model — bigram BoW vector per opportunity."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OpportunityTextEmbedding(Base):
    __tablename__ = "opportunity_text_embeddings"

    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    # Round-15 Sprint 15j cohort 12 — defense-in-depth tenant scoping
    # (backfilled from parent opportunity).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    vocab_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
