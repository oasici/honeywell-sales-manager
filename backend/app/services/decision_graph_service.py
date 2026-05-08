"""Decision graph service.

Plan adoption — Phase 3 / Sprint 14 extension. Layer on top of the existing
``decision_gap_service`` so the gap detector keeps producing per-deal
findings while this service maintains the structural process graph.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.decision_graph import (
    DecisionEdge,
    DecisionNode,
    NODE_STATES,
    NODE_TYPES,
)
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.tenant_context import assert_same_tenant


# Default scaffold the service installs when an opportunity is first
# instrumented. Each tuple = (node_type, label, edges_from).
_DEFAULT_SCAFFOLD: list[tuple[str, str, list[str]]] = [
    ("champion_check", "Şampiyon doğrulandı", []),
    ("technical_evaluation", "Teknik değerlendirme", ["champion_check"]),
    ("budget_approval", "Bütçe onayı", ["technical_evaluation"]),
    ("security_review", "Güvenlik incelemesi", ["technical_evaluation"]),
    ("legal_review", "Hukuki inceleme", ["budget_approval"]),
    ("procurement", "Tedarik / satın alma", ["legal_review", "security_review"]),
    ("executive_sponsor", "Yönetici sponsor", ["budget_approval"]),
    ("compliance", "Uyum", ["legal_review"]),
]


async def _load_opp(db: AsyncSession, opportunity_id: int, current_user: User) -> Opportunity:
    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if opp is None:
        raise NotFoundException("Firsat bulunamadi")
    assert_same_tenant(opp, current_user, exception_cls=NotFoundException)
    return opp


def _node_dict(n: DecisionNode) -> dict[str, Any]:
    return {
        "id": n.id,
        "opportunity_id": n.opportunity_id,
        "node_type": n.node_type,
        "label": n.label,
        "state": n.state,
        "owner_stakeholder_id": n.owner_stakeholder_id,
        "blocker_reason": n.blocker_reason,
        "last_progress_at": n.last_progress_at.isoformat() if n.last_progress_at else None,
        "completed_at": n.completed_at.isoformat() if n.completed_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


def _edge_dict(e: DecisionEdge) -> dict[str, Any]:
    return {
        "id": e.id,
        "opportunity_id": e.opportunity_id,
        "from_node_id": e.from_node_id,
        "to_node_id": e.to_node_id,
        "edge_type": e.edge_type,
        "is_satisfied": bool(e.is_satisfied),
    }


async def get_graph(
    db: AsyncSession, opportunity_id: int, current_user: User
) -> dict[str, Any]:
    opp = await _load_opp(db, opportunity_id, current_user)

    nodes = (
        await db.execute(
            select(DecisionNode).where(DecisionNode.opportunity_id == opportunity_id)
        )
    ).scalars().all()

    edges = (
        await db.execute(
            select(DecisionEdge).where(DecisionEdge.opportunity_id == opportunity_id)
        )
    ).scalars().all()

    progress = _compute_progress(list(nodes))
    return {
        "opportunity_id": opp.id,
        "nodes": [_node_dict(n) for n in nodes],
        "edges": [_edge_dict(e) for e in edges],
        "progress": progress,
    }


async def initialize_default(
    db: AsyncSession, opportunity_id: int, current_user: User
) -> dict[str, Any]:
    """Install the default scaffold if no nodes exist yet for this opp.

    Idempotent — calling twice returns the existing graph unchanged.
    """
    opp = await _load_opp(db, opportunity_id, current_user)

    existing = (
        await db.execute(
            select(DecisionNode).where(DecisionNode.opportunity_id == opportunity_id)
        )
    ).scalars().all()
    if existing:
        return await get_graph(db, opportunity_id, current_user)

    node_by_type: dict[str, DecisionNode] = {}
    for node_type, label, _deps in _DEFAULT_SCAFFOLD:
        node = DecisionNode(
            tenant_id=opp.tenant_id,
            opportunity_id=opportunity_id,
            node_type=node_type,
            label=label,
            state="not_started",
        )
        db.add(node)
        await db.flush()
        node_by_type[node_type] = node

    for node_type, _label, deps in _DEFAULT_SCAFFOLD:
        target = node_by_type[node_type]
        for dep_type in deps:
            source = node_by_type.get(dep_type)
            if source is None:
                continue
            db.add(
                DecisionEdge(
                    tenant_id=opp.tenant_id,
                    opportunity_id=opportunity_id,
                    from_node_id=source.id,
                    to_node_id=target.id,
                    edge_type="sequential",
                )
            )

    await db.flush()
    return await get_graph(db, opportunity_id, current_user)


async def update_node_state(
    db: AsyncSession,
    opportunity_id: int,
    node_id: int,
    *,
    state: str,
    blocker_reason: str | None,
    current_user: User,
) -> dict[str, Any]:
    if state not in NODE_STATES:
        raise BadRequestException("Gecersiz state")

    await _load_opp(db, opportunity_id, current_user)

    node = (
        await db.execute(
            select(DecisionNode).where(
                and_(
                    DecisionNode.id == node_id,
                    DecisionNode.opportunity_id == opportunity_id,
                )
            )
        )
    ).scalar_one_or_none()
    if node is None:
        raise NotFoundException("Karar dugumu bulunamadi")

    node.state = state
    node.blocker_reason = blocker_reason if state == "blocked" else None
    node.last_progress_at = datetime.now(timezone.utc)
    if state == "complete":
        node.completed_at = datetime.now(timezone.utc)
        # Mark edges leaving this node as satisfied so downstream nodes unblock.
        out_edges = (
            await db.execute(
                select(DecisionEdge).where(DecisionEdge.from_node_id == node.id)
            )
        ).scalars().all()
        for edge in out_edges:
            edge.is_satisfied = True

    await db.flush()
    return _node_dict(node)


def _compute_progress(nodes: list[DecisionNode]) -> dict[str, Any]:
    total = len(nodes)
    if not total:
        return {"total": 0, "complete": 0, "blocked": 0, "in_progress": 0, "ratio": 0.0}
    by_state: dict[str, int] = {}
    for n in nodes:
        by_state[n.state] = by_state.get(n.state, 0) + 1
    complete = by_state.get("complete", 0)
    return {
        "total": total,
        "complete": complete,
        "blocked": by_state.get("blocked", 0),
        "in_progress": by_state.get("in_progress", 0),
        "skipped": by_state.get("skipped", 0),
        "ratio": round(complete / total, 2) if total else 0.0,
    }


SUPPORTED_NODE_TYPES = NODE_TYPES
SUPPORTED_NODE_STATES = NODE_STATES
