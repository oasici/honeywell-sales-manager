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
) -> None:
    """Log an activity event. Fire-and-forget — never raises."""
    try:
        from app.models.activity_log import ActivityLog

        entry = ActivityLog(
            activity_type=activity_type,
            entity_type=entity_type,
            entity_id=entity_id,
            opportunity_id=opportunity_id,
            customer_id=customer_id,
            user_id=user_id,
            summary=summary[:500] if summary else "",
            metadata_json=json.dumps(metadata, default=str) if metadata else None,
            created_at=datetime.now(timezone.utc),
        )
        db.add(entry)

        # Also create OpportunityEvent for unified opportunity timeline
        if opportunity_id:
            await _create_opportunity_event(
                db,
                opportunity_id=opportunity_id,
                activity_type=activity_type,
                entity_type=entity_type,
                entity_id=entity_id,
                summary=summary,
            )

        await db.flush()
    except Exception as exc:
        logger.debug("Activity logging failed (non-critical): %s", exc)


_ACTIVITY_TO_EVENT_TYPE = {
    "email_received": "email",
    "email_parsed": "email",
    "quote_created": "quote",
    "quote_approved": "quote",
    "quote_sent": "quote",
    "task_created": "task",
    "task_completed": "task",
    "stage_change": "stage_change",
    "note_added": "note",
    "transcript_uploaded": "meeting",
}


async def _create_opportunity_event(
    db: AsyncSession,
    *,
    opportunity_id: int,
    activity_type: str,
    entity_type: str,
    entity_id: int,
    summary: str,
) -> None:
    """Create a corresponding OpportunityEvent entry."""
    from app.models.opportunity import OpportunityEvent

    event_type = _ACTIVITY_TO_EVENT_TYPE.get(activity_type, activity_type)
    event = OpportunityEvent(
        opportunity_id=opportunity_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        description=summary[:500] if summary else None,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
