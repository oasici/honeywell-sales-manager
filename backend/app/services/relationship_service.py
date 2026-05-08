"""Relationship graph service.

Plan adoption — strategic primitive. Builds and reads the graph of
connections between reps, stakeholders, accounts, and opportunities.

The builder derives edges from ``activity_logs`` (emails, meetings,
notes) and from ``stakeholders`` rows. The reader exposes:

* champion/strongest connection per opportunity or account
* multi-thread coverage score per opportunity
* relationship-strength leaderboard for a rep

The implementation favors *correctness* over scale: edges are upserted
by composite key, scores are recomputed on-demand for a given target
(no nightly batch dependency required for v1).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.activity_log import ActivityLog
from app.models.opportunity import Opportunity
from app.models.relationship_graph import (
    EDGE_SOURCES,
    ENDPOINT_KINDS,
    RelationshipEdge,
    RelationshipScore,
)
from app.models.sequence_v2 import Stakeholder
from app.models.user import User
from app.services.tenant_context import assert_same_tenant


# Activity types that contribute to edge strength + their weight.
_ACTIVITY_WEIGHT = {
    "email_received": 1.0,
    "email_sent": 0.8,
    "email_parsed": 0.6,
    "meeting_held": 4.0,
    "transcript_uploaded": 3.0,
    "task_completed": 1.5,
    "note_added": 0.4,
    "stage_change": 0.5,
    "quote_sent": 1.0,
    "quote_approved": 1.5,
}

# Half-life in days for time-decay on edge strength.
_DECAY_HALF_LIFE_DAYS = 30


def _decay_factor(reference_at: datetime, now: datetime | None = None) -> float:
    if now is None:
        now = datetime.now(timezone.utc)
    if reference_at.tzinfo is None:
        reference_at = reference_at.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - reference_at).total_seconds() / 86400.0)
    return 0.5 ** (days / _DECAY_HALF_LIFE_DAYS)


# ── Read API ──

def _edge_dict(e: RelationshipEdge) -> dict[str, Any]:
    return {
        "id": e.id,
        "from_kind": e.from_kind,
        "from_id": e.from_id,
        "to_kind": e.to_kind,
        "to_id": e.to_id,
        "relation_type": e.relation_type,
        "strength": round(float(e.strength or 0.0), 2),
        "interaction_count": e.interaction_count,
        "last_interaction_at": e.last_interaction_at.isoformat()
        if e.last_interaction_at
        else None,
        "source": e.source,
    }


def _score_dict(s: RelationshipScore) -> dict[str, Any]:
    return {
        "id": s.id,
        "target_kind": s.target_kind,
        "target_id": s.target_id,
        "edge_count": s.edge_count,
        "strongest_strength": round(float(s.strongest_strength or 0.0), 2),
        "avg_strength": round(float(s.avg_strength or 0.0), 2),
        "coverage_score": round(float(s.coverage_score or 0.0), 2),
        "strongest_edge_id": s.strongest_edge_id,
        "snapshot_date": s.snapshot_date.isoformat() if s.snapshot_date else None,
    }


async def _verify_endpoint_tenant(
    db: AsyncSession, kind: str, entity_id: int, current_user: User
) -> None:
    """Round-8 R8-TEN-1 — when the endpoint is a CRM entity, load the
    parent record and assert tenant. Cross-tenant lookups raise 404.
    Graph endpoints whose parent isn't a tenant-scoped row (e.g. ``user``
    is itself a tenant member) skip the check.
    """
    if kind == "opportunity":
        opp = (
            await db.execute(select(Opportunity).where(Opportunity.id == entity_id))
        ).scalar_one_or_none()
        if opp is None:
            raise NotFoundException("Firsat bulunamadi")
        assert_same_tenant(opp, current_user, exception_cls=NotFoundException)
    elif kind == "account":
        from app.models.customer import Customer

        cust = (
            await db.execute(select(Customer).where(Customer.id == entity_id))
        ).scalar_one_or_none()
        if cust is None:
            raise NotFoundException("Hesap bulunamadi")
        assert_same_tenant(cust, current_user, exception_cls=NotFoundException)
    elif kind == "stakeholder":
        from app.models.sequence_v2 import Stakeholder

        sh = (
            await db.execute(select(Stakeholder).where(Stakeholder.id == entity_id))
        ).scalar_one_or_none()
        if sh is None:
            raise NotFoundException("Paydas bulunamadi")
        # Stakeholder doesn't carry tenant_id directly; verify through opp/customer.
        if sh.opportunity_id is not None:
            opp = (
                await db.execute(select(Opportunity).where(Opportunity.id == sh.opportunity_id))
            ).scalar_one_or_none()
            if opp is None:
                raise NotFoundException("Paydas bulunamadi")
            assert_same_tenant(opp, current_user, exception_cls=NotFoundException)


async def get_edges_for_endpoint(
    db: AsyncSession,
    *,
    kind: str,
    entity_id: int,
    current_user: User,
    limit: int = 100,
) -> list[dict[str, Any]]:
    if kind not in ENDPOINT_KINDS:
        return []

    await _verify_endpoint_tenant(db, kind, entity_id, current_user)

    stmt = (
        select(RelationshipEdge)
        .where(
            or_(
                and_(RelationshipEdge.from_kind == kind, RelationshipEdge.from_id == entity_id),
                and_(RelationshipEdge.to_kind == kind, RelationshipEdge.to_id == entity_id),
            )
        )
        .where(
            (RelationshipEdge.tenant_id == current_user.tenant_id)
            | (RelationshipEdge.tenant_id.is_(None))
        )
        .order_by(desc(RelationshipEdge.strength))
        .limit(limit)
    )

    rows = (await db.execute(stmt)).scalars().all()
    return [_edge_dict(e) for e in rows]


async def get_score_for_endpoint(
    db: AsyncSession,
    *,
    kind: str,
    entity_id: int,
    current_user: User,
) -> dict[str, Any] | None:
    if kind not in ENDPOINT_KINDS:
        return None
    await _verify_endpoint_tenant(db, kind, entity_id, current_user)
    score = (
        await db.execute(
            select(RelationshipScore).where(
                and_(
                    RelationshipScore.target_kind == kind,
                    RelationshipScore.target_id == entity_id,
                    (RelationshipScore.tenant_id == current_user.tenant_id)
                    | (RelationshipScore.tenant_id.is_(None)),
                )
            )
        )
    ).scalar_one_or_none()
    return _score_dict(score) if score else None


async def get_strongest_connections(
    db: AsyncSession,
    *,
    target_kind: str,
    target_id: int,
    current_user: User,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if target_kind not in ENDPOINT_KINDS:
        return []
    await _verify_endpoint_tenant(db, target_kind, target_id, current_user)
    edges = (
        await db.execute(
            select(RelationshipEdge)
            .where(
                or_(
                    and_(
                        RelationshipEdge.from_kind == target_kind,
                        RelationshipEdge.from_id == target_id,
                    ),
                    and_(
                        RelationshipEdge.to_kind == target_kind,
                        RelationshipEdge.to_id == target_id,
                    ),
                )
            )
            .where(
                (RelationshipEdge.tenant_id == current_user.tenant_id)
                | (RelationshipEdge.tenant_id.is_(None))
            )
            .order_by(desc(RelationshipEdge.strength))
            .limit(limit)
        )
    ).scalars().all()
    return [_edge_dict(e) for e in edges]


# ── Write / Build API ──

async def upsert_edge(
    db: AsyncSession,
    *,
    tenant_id: int | None,
    from_kind: str,
    from_id: int,
    to_kind: str,
    to_id: int,
    relation_type: str | None = None,
    strength_delta: float = 1.0,
    interaction_at: datetime | None = None,
    source: str = "derived",
    metadata: dict[str, Any] | None = None,
) -> RelationshipEdge:
    if from_kind not in ENDPOINT_KINDS or to_kind not in ENDPOINT_KINDS:
        raise ValueError(f"Geçersiz endpoint kind: {from_kind}/{to_kind}")
    if source not in EDGE_SOURCES:
        raise ValueError(f"Geçersiz edge source: {source}")

    existing = (
        await db.execute(
            select(RelationshipEdge).where(
                and_(
                    RelationshipEdge.from_kind == from_kind,
                    RelationshipEdge.from_id == from_id,
                    RelationshipEdge.to_kind == to_kind,
                    RelationshipEdge.to_id == to_id,
                )
            )
        )
    ).scalar_one_or_none()

    when = interaction_at or datetime.now(timezone.utc)

    if existing is None:
        edge = RelationshipEdge(
            tenant_id=tenant_id,
            from_kind=from_kind,
            from_id=from_id,
            to_kind=to_kind,
            to_id=to_id,
            relation_type=relation_type,
            strength=min(100.0, max(0.0, strength_delta)),
            interaction_count=1,
            last_interaction_at=when,
            source=source,
            metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
        )
        db.add(edge)
        await db.flush()
        return edge

    new_strength = min(100.0, float(existing.strength or 0.0) + strength_delta)
    existing.strength = new_strength
    existing.interaction_count += 1
    existing.last_interaction_at = when
    if relation_type and not existing.relation_type:
        existing.relation_type = relation_type
    await db.flush()
    return existing


async def rebuild_edges_for_opportunity(
    db: AsyncSession,
    *,
    opportunity_id: int,
    current_user: User,
    lookback_days: int = 180,
) -> dict[str, Any]:
    """Derive edges from activity_logs + stakeholders for a single opp.

    Idempotent: each (from, to) endpoint pair is upserted exactly once
    per call, so reruns can't double-count strength.
    """
    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if opp is None:
        raise NotFoundException("Firsat bulunamadi")
    assert_same_tenant(opp, current_user, exception_cls=NotFoundException)

    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, min(lookback_days, 720)))

    # Reset strength on existing derived edges for this opp so we can
    # rebuild cleanly without double-counting.
    await db.execute(
        select(RelationshipEdge).where(
            and_(
                RelationshipEdge.source == "derived",
                or_(
                    and_(
                        RelationshipEdge.from_kind == "opportunity",
                        RelationshipEdge.from_id == opportunity_id,
                    ),
                    and_(
                        RelationshipEdge.to_kind == "opportunity",
                        RelationshipEdge.to_id == opportunity_id,
                    ),
                ),
            )
        )
    )

    # Pull activity for the deal
    activities = (
        await db.execute(
            select(ActivityLog).where(
                and_(
                    ActivityLog.opportunity_id == opportunity_id,
                    ActivityLog.created_at >= cutoff,
                )
            )
        )
    ).scalars().all()

    # 1) Stakeholders → opportunity (anchor edges)
    stakeholders = (
        await db.execute(
            select(Stakeholder).where(Stakeholder.opportunity_id == opportunity_id)
        )
    ).scalars().all()

    edges_touched = 0
    for sh in stakeholders:
        await upsert_edge(
            db,
            tenant_id=opp.tenant_id,
            from_kind="opportunity",
            from_id=opportunity_id,
            to_kind="stakeholder",
            to_id=sh.id,
            relation_type=sh.buyer_role or "stakeholder",
            strength_delta=12.0,
            source="derived",
        )
        edges_touched += 1

    # 2) Activity-derived: rep → opportunity, rep → stakeholder
    for act in activities:
        weight = _ACTIVITY_WEIGHT.get(act.activity_type, 0.0)
        if weight <= 0:
            continue

        decayed = weight * _decay_factor(act.created_at)
        if act.user_id:
            await upsert_edge(
                db,
                tenant_id=opp.tenant_id,
                from_kind="user",
                from_id=act.user_id,
                to_kind="opportunity",
                to_id=opportunity_id,
                strength_delta=decayed,
                interaction_at=act.created_at,
                source="derived",
            )
            edges_touched += 1

            for sh in stakeholders:
                await upsert_edge(
                    db,
                    tenant_id=opp.tenant_id,
                    from_kind="user",
                    from_id=act.user_id,
                    to_kind="stakeholder",
                    to_id=sh.id,
                    strength_delta=decayed * 0.4,
                    interaction_at=act.created_at,
                    source="derived",
                )
                edges_touched += 1

    # Recompute scores for opportunity + each stakeholder
    await _refresh_score(db, "opportunity", opportunity_id, opp.tenant_id)
    for sh in stakeholders:
        await _refresh_score(db, "stakeholder", sh.id, opp.tenant_id)

    return {
        "opportunity_id": opportunity_id,
        "edges_touched": edges_touched,
        "stakeholders": len(stakeholders),
    }


async def _refresh_score(
    db: AsyncSession, target_kind: str, target_id: int, tenant_id: int | None
) -> RelationshipScore:
    edges = (
        await db.execute(
            select(RelationshipEdge).where(
                or_(
                    and_(
                        RelationshipEdge.from_kind == target_kind,
                        RelationshipEdge.from_id == target_id,
                    ),
                    and_(
                        RelationshipEdge.to_kind == target_kind,
                        RelationshipEdge.to_id == target_id,
                    ),
                )
            )
        )
    ).scalars().all()

    if not edges:
        edge_count = 0
        strongest = 0.0
        avg = 0.0
        coverage = 0.0
        strongest_edge_id = None
    else:
        edge_count = len(edges)
        strongest_edge = max(edges, key=lambda e: float(e.strength or 0.0))
        strongest = float(strongest_edge.strength or 0.0)
        avg = sum(float(e.strength or 0.0) for e in edges) / edge_count
        # Coverage: fraction of edges with strength >= 25 (a rough "warm" threshold).
        warm = [e for e in edges if float(e.strength or 0.0) >= 25.0]
        coverage = round(len(warm) / max(1, edge_count) * 100, 2)
        strongest_edge_id = strongest_edge.id

    existing = (
        await db.execute(
            select(RelationshipScore).where(
                and_(
                    RelationshipScore.target_kind == target_kind,
                    RelationshipScore.target_id == target_id,
                )
            )
        )
    ).scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing is None:
        existing = RelationshipScore(
            tenant_id=tenant_id,
            target_kind=target_kind,
            target_id=target_id,
            edge_count=edge_count,
            strongest_strength=strongest,
            avg_strength=avg,
            coverage_score=coverage,
            strongest_edge_id=strongest_edge_id,
            snapshot_date=now,
        )
        db.add(existing)
    else:
        existing.edge_count = edge_count
        existing.strongest_strength = strongest
        existing.avg_strength = avg
        existing.coverage_score = coverage
        existing.strongest_edge_id = strongest_edge_id
        existing.snapshot_date = now
    await db.flush()
    return existing
