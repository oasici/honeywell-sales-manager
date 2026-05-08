"""Relationship graph (plan adoption — strategic primitive).

Models how people inside the customer org are connected to our reps and to
each other. Three concrete uses:

1. **Champion detection** — strongest stakeholder ↔ rep edge
2. **Multi-thread coverage** — count of distinct stakeholder edges per opp
3. **Influence mapping** — internal stakeholder ↔ stakeholder graph

The plan also asks for ``relationship_scores``: per-(rep, stakeholder) or
per-(account, opportunity) rolled-up scores derived from the edges. We
keep that as a separate table so the rollups can decay/expire cleanly
without rewriting the edge log.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# Edge endpoint kinds. Keep tight; the service layer routes on these.
ENDPOINT_KINDS = (
    "user",          # internal rep
    "stakeholder",   # external person at customer org
    "account",       # the customer account itself
    "opportunity",   # an opportunity row
)

# How the edge was inferred. ``derived`` = computed from activity log.
EDGE_SOURCES = ("derived", "manual", "import", "ai")


class RelationshipEdge(Base):
    """A directed connection between two graph endpoints.

    The graph is generic: ``(from_kind, from_id) -> (to_kind, to_id)``.
    Strength accumulates from interactions (emails, meetings, replies);
    decay is applied by the nightly builder, not in this row.
    """

    __tablename__ = "relationship_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    from_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    from_id: Mapped[int] = mapped_column(Integer, nullable=False)
    to_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    to_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # The role this edge plays — champion, sponsor, decision_maker, etc.
    # Free-form so the service can experiment without migrations.
    relation_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    # Round-8 R8-DB-2 — server_default for create_all()/bootstrap parity.
    strength: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    interaction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_interaction_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="derived", server_default="derived"
    )
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "from_kind", "from_id", "to_kind", "to_id", name="uq_rel_edge_endpoints"
        ),
        Index("ix_rel_edge_from", "from_kind", "from_id"),
        Index("ix_rel_edge_to", "to_kind", "to_id"),
        Index("ix_rel_edge_strength", "strength"),
    )


class RelationshipScore(Base):
    """Daily-cadence rollup of relationship strength for a target endpoint.

    Used by the dashboard ("strongest connection at Acme Corp") and the
    decision-gap detector ("we have no champion-grade edge here yet").
    Materialized by the nightly builder; not user-edited.
    """

    __tablename__ = "relationship_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    target_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Aggregate metrics across edges with this target endpoint.
    # Round-8 R8-DB-2 — server_default propagated for bootstrap parity.
    edge_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    strongest_strength: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    avg_strength: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    coverage_score: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0, server_default="0"
    )
    # The single best edge id, denormalized for fast lookups.
    strongest_edge_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("relationship_edges.id"), nullable=True
    )
    snapshot_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint("target_kind", "target_id", name="uq_rel_score_target"),
        Index("ix_rel_score_kind", "target_kind"),
    )
