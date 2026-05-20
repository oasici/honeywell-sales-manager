"""V12 transformer-based sequence embedding per opportunity.

Mirrors :class:`OpportunityTextEmbedding` (V8 BoW) but stores the
transformer-derived vector. We keep them in **separate** tables
rather than overwriting the V8 row because:

- The blend logic in ``deal_similarity_service`` consumes both
  vectors when available and falls back gracefully when only V8
  exists. Sharing one row would force every deployment to
  re-encode after every code/version bump.
- Different lifecycles: V8 is deterministic and cheap to recompute;
  V12 needs the transformer model loaded.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OpportunityTransformerSeqEmbedding(Base):
    __tablename__ = "opportunity_transformer_seq_embeddings"

    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    # Round-15 Sprint 15j cohort 12 — defense-in-depth tenant scoping
    # (backfilled from parent opportunity).
    # Round-15 Sprint 15r cohort 8 — promoted to NOT NULL.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    vocab_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
