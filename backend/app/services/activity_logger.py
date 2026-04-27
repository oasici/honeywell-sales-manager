"""Unified activity logging service.

Auto-captures events from email, quote, opportunity, and task operations.
Also creates OpportunityEvent when opportunity_id is provided (unified timeline).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def log_activity(
    db: AsyncSession,
    *,
    activity_type: str,
    entity_type: str,
    entity_id: int,
    opportunity_id: int | None = None,
    customer_id: int | None = None,
    user_id: int | None = None,
    summary: str = "",
    metadata: dict | None = None,
    source_ref: str | None = None,
) -> None:
    """Log an activity event. Fire-and-forget — never raises."""
    try:
        from app.models.activity_log import ActivityLog
        from sqlalchemy import select
        from app.core.event_registry import validate_activity_entity, opportunity_event_type_for

        if not validate_activity_entity(activity_type, entity_type):
            logger.debug(
                "Activity entity mismatch type=%s entity_type=%s", activity_type, entity_type
            )

        # Optional idempotency: if source_ref present, skip duplicates.
        # This is best-effort; no hard uniqueness constraint (yet).
        if source_ref:
            existing = await db.execute(
                select(ActivityLog.id).where(
                    ActivityLog.source_ref == source_ref,
                    ActivityLog.activity_type == activity_type,
                    ActivityLog.entity_type == entity_type,
                    ActivityLog.entity_id == entity_id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                return

        if metadata is None:
            metadata = {}
        if source_ref:
            metadata.setdefault("source_ref", source_ref)

        entry = ActivityLog(
            activity_type=activity_type,
            entity_type=entity_type,
            entity_id=entity_id,
            opportunity_id=opportunity_id,
            customer_id=customer_id,
            user_id=user_id,
            summary=summary[:500] if summary else "",
            metadata_json=json.dumps(metadata, default=str) if metadata else None,
            source_ref=source_ref,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)

        # Also create OpportunityEvent for unified opportunity timeline
        if opportunity_id:
            await _create_opportunity_event(
                db,
                opportunity_id=opportunity_id,
                event_type=opportunity_event_type_for(activity_type),
                entity_type=entity_type,
                entity_id=entity_id,
                summary=summary,
            )

        await db.flush()

        # V6: real-time recompute hook. Best-effort — failures here
        # never propagate to the caller (the event is already
        # persisted). Gated by FEATURE_V6_REALTIME so old behaviour
        # is preserved when the flag is off.
        try:
            from app.services.event_recompute_hooks import recompute_after_activity

            await recompute_after_activity(db, opportunity_id=opportunity_id)
        except Exception as hook_exc:
            logger.debug("V6 recompute hook failed (non-critical): %s", hook_exc)
    except Exception as exc:
        logger.debug("Activity logging failed (non-critical): %s", exc)


async def _create_opportunity_event(
    db: AsyncSession,
    *,
    opportunity_id: int,
    event_type: str,
    entity_type: str,
    entity_id: int,
    summary: str,
) -> None:
    """Create a corresponding OpportunityEvent entry."""
    from app.models.opportunity import OpportunityEvent

    event = OpportunityEvent(
        opportunity_id=opportunity_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        description=summary[:500] if summary else None,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
