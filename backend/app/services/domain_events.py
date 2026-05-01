"""Domain event constants, schemas, and persistence helpers.

Central registry of all domain events emitted by the system. Each event
has a type string, an expected payload shape, and an optional persistence
flag (write to domain_events table for audit).

Usage:
    from app.services.domain_events import emit_domain_event, DomainEvents
    await emit_domain_event(db, DomainEvents.SEQUENCE_STEP_COMPLETED, {...})
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DomainEvents:
    """Event type constants — single source of truth for event names."""

    # ── Sequence lifecycle ──
    SEQUENCE_STEP_COMPLETED = "sequence.step_completed"
    SEQUENCE_COMPLETED = "sequence.completed"
    SEQUENCE_EXITED = "sequence.exited"
    SEQUENCE_ENROLLED = "sequence.enrolled"
    SEQUENCE_ENROLLED_AUTO = "sequence.enrolled_auto"
    SEQUENCE_PAUSED = "sequence.paused"
    SEQUENCE_RESUMED = "sequence.resumed"

    # ── Scoring ──
    LEAD_SCORE_CHANGED = "lead.score_changed"
    OPP_SCORE_CHANGED = "opportunity.score_changed"

    # ── Existing events (already in event bus, listed for reference) ──
    EMAIL_PARSED = "email.parsed"
    QUOTE_SENT = "quote.sent"
    QUOTE_APPROVED = "quote.approved"
    OPP_STAGE_CHANGED = "opportunity.stage_changed"
    OPP_CREATED = "opportunity.created"
    LEAD_CONVERTED = "lead.converted"
    CUSTOMER_CREATED = "customer.created"
    SIGNAL_CREATED = "revenue_signal.created"


# ── Payload schemas (documentation, not runtime validation) ──

EVENT_PAYLOAD_SCHEMAS: dict[str, dict] = {
    DomainEvents.SEQUENCE_STEP_COMPLETED: {
        "enrollment_id": "int",
        "sequence_id": "int",
        "step_number": "int",
        "step_action": "str",
        "variant_key": "str|None",
        "opportunity_id": "int|None",
        "customer_id": "int|None",
        "lead_id": "int|None",
    },
    DomainEvents.SEQUENCE_COMPLETED: {
        "enrollment_id": "int",
        "sequence_id": "int",
        "exit_reason": "str",
        "total_steps": "int",
        "opportunity_id": "int|None",
        "customer_id": "int|None",
        "lead_id": "int|None",
    },
    DomainEvents.SEQUENCE_EXITED: {
        "enrollment_id": "int",
        "sequence_id": "int",
        "exit_reason": "str",
        "current_step": "int",
        "opportunity_id": "int|None",
        "customer_id": "int|None",
        "lead_id": "int|None",
    },
    DomainEvents.LEAD_SCORE_CHANGED: {
        "lead_id": "int",
        "old_score": "float|None",
        "new_score": "float",
        "reason": "str",
    },
    DomainEvents.SIGNAL_CREATED: {
        "signal_id": "int",
        "signal_type": "str",
        "severity": "str",
        "opportunity_id": "int|None",
        "depth": "int|None",
    },
}


async def emit_domain_event(
    db: AsyncSession,
    event_type: str,
    payload: dict,
    *,
    entity_type: str | None = None,
    entity_id: int | None = None,
    actor_id: int | None = None,
    persist: bool = True,
) -> None:
    """Emit a domain event: persist to DB + publish to in-process event bus.

    Args:
        db: Active database session (caller must commit).
        event_type: Event type constant from DomainEvents.
        payload: Event payload dict.
        entity_type: Optional entity type for indexing.
        entity_id: Optional entity ID for indexing.
        actor_id: Optional acting user ID.
        persist: Whether to write to domain_events table (default True).
    """
    if persist:
        from app.models.sequence_v2 import DomainEvent

        event = DomainEvent(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            payload_json=json.dumps(payload, default=str),
            actor_id=actor_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(event)

    # Publish to in-process event bus (fire-and-forget, never raises)
    try:
        from app.core.event_bus import event_bus

        await event_bus.publish(event_type, payload)
    except Exception as exc:
        logger.warning("Event bus publish failed for %s: %s", event_type, exc)
