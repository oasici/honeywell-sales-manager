"""V5 deal similarity + rep DNA profile models."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OpportunityEmbedding(Base):
    """Structured-feature vector per opportunity (JSON-encoded floats)."""

    __tablename__ = "opportunity_embeddings"

    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), primary_key=True
    )
    # Round-15 Sprint 15j cohort 7 — defense-in-depth tenant scoping.
    # Round-15 Sprint 15o cohort 5 — promoted to NOT NULL.
    # opportunity_id is the PK on this row and ``opportunities.tenant_id``
    # is NOT NULL since Sprint 15k cohort 1.
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[str] = mapped_column(String(40), default="v5-structured-1")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class DealSimilarityLink(Base):
    __tablename__ = "deal_similarity_links"
    __table_args__ = (UniqueConstraint("opportunity_id", "similar_opportunity_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id", ondelete="CASCADE"), index=True
    )
    similar_opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id", ondelete="CASCADE")
    )
    # Round-15 Sprint 15j cohort 7 — defense-in-depth tenant scoping
    # (backfilled from parent opportunity).
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    similarity_reason_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class RepDnaProfile(Base):
    __tablename__ = "rep_dna_profiles"

    rep_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    cluster_label: Mapped[str] = mapped_column(String(40), nullable=False)
    profile_json: Mapped[str] = mapped_column(Text, default="{}")
    strengths_json: Mapped[str] = mapped_column(Text, default="[]")
    gaps_json: Mapped[str] = mapped_column(Text, default="[]")
    sample_period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    sample_period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
