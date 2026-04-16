"""Revenue Signal Service — emit, query, resolve unified signals.

This is the single source of truth for the Revenue Cockpit.
All CRM/Signal/Transaction events flow through emit_signal().
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.revenue_signal import RevenueSignal

logger = logging.getLogger(__name__)

MAX_CASCADE_DEPTH = 3


async def emit_signal(
    db: AsyncSession,
    *,
    signal_type: str,
    source_entity_type: str,
    source_entity_id: int | None = None,
    opportunity_id: int | None = None,
    customer_id: int | None = None,
    owner_id: int | None = None,
    severity: str = "med",
    confidence: float = 0.5,
    recommended_action: str | None = None,
    metadata: dict | None = None,
    depth: int = 0,
    event_key: str | None = None,
) -> RevenueSignal | None:
    """Emit a canonical revenue signal. Idempotent via event_key.

    Returns None if deduplicated or depth exceeded.
    """
    # Cascade guard
    if depth > MAX_CASCADE_DEPTH:
        logger.debug("Signal depth %d exceeds max %d, dropping", depth, MAX_CASCADE_DEPTH)
        return None

    # Idempotency: skip if event_key already exists
    if event_key:
        existing = await db.execute(
            select(RevenueSignal.id).where(RevenueSignal.event_key == event_key)
        )
        if existing.scalar_one_or_none() is not None:
            logger.debug("Duplicate signal event_key=%s, skipping", event_key)
            return None

    signal = RevenueSignal(
        signal_type=signal_type,
        source_entity_type=source_entity_type,
        source_entity_id=source_entity_id,
        opportunity_id=opportunity_id,
        customer_id=customer_id,
        owner_id=owner_id,
        severity=severity,
        confidence=confidence,
        recommended_action=recommended_action,
        metadata_json=json.dumps(metadata, default=str) if metadata else None,
        depth=depth,
        event_key=event_key,
    )
    db.add(signal)
    await db.flush()

    # Publish to event bus (non-blocking, for downstream: playbook eval, webhooks)
    try:
        from app.core.event_bus import event_bus
        await event_bus.publish("revenue_signal.created", {
            "signal_id": signal.id,
            "signal_type": signal_type,
            "severity": severity,
            "opportunity_id": opportunity_id,
            "depth": depth,
        })
    except Exception as exc:
        logger.debug("Event bus publish failed (non-critical): %s", exc)

    return signal


async def get_signal_stream(
    db: AsyncSession,
    *,
    owner_id: int | None = None,
    opportunity_id: int | None = None,
    customer_id: int | None = None,
    severity: str | None = None,
    signal_type: str | None = None,
    include_resolved: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Paginated signal stream for cockpit. Returns {items, total}."""
    conditions = []
    if owner_id:
        conditions.append(RevenueSignal.owner_id == owner_id)
    if opportunity_id:
        conditions.append(RevenueSignal.opportunity_id == opportunity_id)
    if customer_id:
        conditions.append(RevenueSignal.customer_id == customer_id)
    if severity:
        conditions.append(RevenueSignal.severity == severity)
    if signal_type:
        conditions.append(RevenueSignal.signal_type == signal_type)
    if not include_resolved:
        conditions.append(RevenueSignal.is_resolved.is_(False))

    where = and_(*conditions) if conditions else True

    total = (await db.execute(select(func.count(RevenueSignal.id)).where(where))).scalar() or 0

    result = await db.execute(
        select(RevenueSignal)
        .where(where)
        .order_by(RevenueSignal.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    signals = result.scalars().all()

    return {
        "items": [_signal_to_dict(s) for s in signals],
        "total": total,
    }


async def get_signal_stats(
    db: AsyncSession,
    *,
    owner_id: int | None = None,
    days: int = 30,
) -> dict:
    """Aggregate counts by type and severity for KPI strip."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    conditions = [
        RevenueSignal.created_at >= since,
        RevenueSignal.is_resolved.is_(False),
    ]
    if owner_id:
        conditions.append(RevenueSignal.owner_id == owner_id)

    where = and_(*conditions)

    # Count by severity
    severity_result = await db.execute(
        select(RevenueSignal.severity, func.count(RevenueSignal.id))
        .where(where)
        .group_by(RevenueSignal.severity)
    )
    by_severity = {row[0]: row[1] for row in severity_result.all()}

    # Count by type (top 10)
    type_result = await db.execute(
        select(RevenueSignal.signal_type, func.count(RevenueSignal.id))
        .where(where)
        .group_by(RevenueSignal.signal_type)
        .order_by(func.count(RevenueSignal.id).desc())
        .limit(10)
    )
    by_type = {row[0]: row[1] for row in type_result.all()}

    total = sum(by_severity.values())

    return {
        "total": total,
        "by_severity": by_severity,
        "by_type": by_type,
        "critical_count": by_severity.get("critical", 0),
        "high_count": by_severity.get("high", 0),
    }


async def resolve_signal(db: AsyncSession, signal_id: int) -> bool:
    """Mark a signal as resolved. Returns True if found."""
    result = await db.execute(
        select(RevenueSignal).where(RevenueSignal.id == signal_id)
    )
    signal = result.scalar_one_or_none()
    if not signal:
        return False
    signal.is_resolved = True
    await db.flush()
    return True


def _signal_to_dict(s: RevenueSignal) -> dict:
    return {
        "id": s.id,
        "signal_type": s.signal_type,
        "source_entity_type": s.source_entity_type,
        "source_entity_id": s.source_entity_id,
        "opportunity_id": s.opportunity_id,
        "customer_id": s.customer_id,
        "owner_id": s.owner_id,
        "severity": s.severity,
        "confidence": s.confidence,
        "recommended_action": s.recommended_action,
        "is_resolved": s.is_resolved,
        "created_at": s.created_at.isoformat() if s.created_at else None,
    }
