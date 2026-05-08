"""Decision graph (plan adoption — Phase 3 Sprint 14 extension).

The plan asks for ``decision_nodes`` and ``decision_edges`` to model how
budget approval, security review, procurement, legal review, etc. depend
on each other. We layer this on top of the existing ``decision_gaps`` +
``stakeholder_roles`` machinery rather than replacing it — the gap detector
keeps producing per-opportunity insights, while these tables describe the
structural process every deal in this stage type has to go through.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


# Process node types we model out of the box — keep enum tight.
NODE_TYPES = (
    "budget_approval",
    "security_review",
    "procurement",
    "legal_review",
    "technical_evaluation",
    "executive_sponsor",
    "compliance",
    "champion_check",
)

# Node states across the deal's lifecycle.
NODE_STATES = (
    "not_started",
    "in_progress",
    "blocked",
    "complete",
    "skipped",
)


class DecisionNode(Base):
    """A discrete process step a deal must clear (e.g. legal review).

    One row per (opportunity, node_type). Sequencing comes from
    ``decision_edges``.
    """

    __tablename__ = "decision_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False, index=True
    )
    node_type: Mapped[str] = mapped_column(String(40), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    # Round-8 R8-DB-2 — server_default ensures bootstrap/create_all() emits
    # the DDL DEFAULT clause so raw INSERTs without ``state`` work.
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_started", server_default="not_started"
    )
    owner_stakeholder_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("stakeholders.id"), nullable=True
    )
    blocker_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_progress_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("opportunity_id", "node_type", name="uq_decision_nodes_opp_type"),
        Index("ix_decision_nodes_state", "state"),
    )


class DecisionEdge(Base):
    """Dependency between two decision nodes within the same opportunity.

    ``from_node`` blocks ``to_node`` until the edge is satisfied.
    ``edge_type`` carries the relationship semantics (sequential, parallel,
    optional).
    """

    __tablename__ = "decision_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    opportunity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("opportunities.id"), nullable=False, index=True
    )
    from_node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("decision_nodes.id"), nullable=False, index=True
    )
    to_node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("decision_nodes.id"), nullable=False, index=True
    )
    edge_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="sequential", server_default="sequential"
    )
    is_satisfied: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        UniqueConstraint(
            "opportunity_id", "from_node_id", "to_node_id", name="uq_decision_edges_triple"
        ),
    )
