"""Behavioral Scoring Service — dynamic lead/opportunity scoring from engagement signals.

Gated by FEATURE_BEHAVIORAL_SCORING. Consumes domain events and updates
lead_score on Lead records. Scores are rule-based (v1), not ML.

Positive signals: reply, meeting, quote_progress, positive_keywords
Negative signals: bounce, DNC, no_touch, long_silence, objection_keywords

Score range: 0–100, clamped.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Scoring rules (v1 — deterministic, configurable) ──

POSITIVE_SIGNALS: dict[str, int] = {
    "email_replied": 15,
    "meeting_booked": 20,
    "quote_sent": 10,
    "quote_approved": 15,
    "call_connected": 10,
    "sequence_step_completed": 3,
    "positive_keyword": 5,
}

NEGATIVE_SIGNALS: dict[str, int] = {
    "email_bounced": -20,
    "dnc_flagged": -50,
    "no_touch_7d": -5,
    "no_touch_14d": -10,
    "no_touch_30d": -20,
    "objection_keyword": -5,
    "sequence_exited_unresponsive": -10,
}


async def update_lead_score(
    db: AsyncSession,
    lead_id: int,
    signal_type: str,
    *,
    reason: str | None = None,
) -> dict | None:
    """Update a lead's score based on a behavioral signal.

    Returns {"lead_id", "old_score", "new_score", "delta", "reason"} or None if
    the feature is off or the lead is not found.
    """
    if not settings.FEATURE_BEHAVIORAL_SCORING:
        return None

    from app.models.lead import Lead

    lead = (
        await db.execute(select(Lead).where(Lead.id == lead_id))
    ).scalar_one_or_none()
    if not lead:
        return None

    delta = POSITIVE_SIGNALS.get(signal_type, 0) + NEGATIVE_SIGNALS.get(signal_type, 0)
    if delta == 0:
        return None

    old_score = lead.lead_score or 0
    new_score = max(0, min(100, old_score + delta))
    lead.lead_score = new_score

    result = {
        "lead_id": lead_id,
        "old_score": old_score,
        "new_score": new_score,
        "delta": delta,
        "reason": reason or signal_type,
    }

    # Emit domain event
    from app.services.domain_events import DomainEvents, emit_domain_event

    await emit_domain_event(
        db,
        DomainEvents.LEAD_SCORE_CHANGED,
        result,
        entity_type="lead",
        entity_id=lead_id,
    )

    logger.info(
        "Lead %d score: %d -> %d (signal=%s, delta=%+d)",
        lead_id, old_score, new_score, signal_type, delta,
    )
    return result


async def on_sequence_step_completed(event_type: str, payload: dict) -> None:
    """Event handler: update lead score when a sequence step completes."""
    if not settings.FEATURE_BEHAVIORAL_SCORING:
        return

    lead_id = payload.get("lead_id")
    if not lead_id:
        return

    from app.core.database import async_session

    async with async_session() as db:
        await update_lead_score(
            db,
            lead_id,
            "sequence_step_completed",
            reason=f"step_{payload.get('step_number', '?')}_completed",
        )
        await db.commit()


async def on_sequence_exited(event_type: str, payload: dict) -> None:
    """Event handler: penalize score when sequence exits due to unresponsiveness."""
    if not settings.FEATURE_BEHAVIORAL_SCORING:
        return

    lead_id = payload.get("lead_id")
    exit_reason = payload.get("exit_reason", "")
    if not lead_id:
        return

    # Only penalize for unresponsive exits (all_steps_completed with no conversion)
    if exit_reason == "all_steps_completed":
        from app.core.database import async_session

        async with async_session() as db:
            await update_lead_score(
                db,
                lead_id,
                "sequence_exited_unresponsive",
                reason="sequence_completed_no_conversion",
            )
            await db.commit()


async def evaluate_auto_enroll(
    db: AsyncSession,
    lead_id: int,
) -> list[int]:
    """Check if a lead should be auto-enrolled in any sequence based on score thresholds.

    Returns list of sequence IDs where the lead was enrolled.
    """
    if not settings.FEATURE_BEHAVIORAL_SCORING:
        return []

    from app.models.engagement import Sequence, SequenceEnrollment
    from app.models.lead import Lead

    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    if not lead or lead.status in ("converted", "lost", "cancelled"):
        return []

    # Find sequences with auto_enroll_rules_json
    seqs = (
        await db.execute(
            select(Sequence).where(
                Sequence.is_active.is_(True),
                Sequence.auto_enroll_rules_json.isnot(None),
            )
        )
    ).scalars().all()

    enrolled_in: list[int] = []
    for seq in seqs:
        try:
            rules = json.loads(seq.auto_enroll_rules_json)
        except (json.JSONDecodeError, TypeError):
            continue

        if not _lead_matches_auto_rules(lead, rules):
            continue

        # Check not already enrolled
        existing = (
            await db.execute(
                select(SequenceEnrollment.id).where(
                    SequenceEnrollment.sequence_id == seq.id,
                    SequenceEnrollment.lead_id == lead_id,
                    SequenceEnrollment.status.in_(["active", "paused"]),
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue

        enrollment = SequenceEnrollment(
            sequence_id=seq.id,
            lead_id=lead_id,
            enrolled_by=seq.created_by,
            current_step=1,
            status="active",
            next_action_at=datetime.now(timezone.utc),
        )
        db.add(enrollment)
        enrolled_in.append(seq.id)

        from app.services.domain_events import DomainEvents, emit_domain_event

        await emit_domain_event(
            db,
            DomainEvents.SEQUENCE_ENROLLED_AUTO,
            {
                "enrollment_id": None,  # not yet flushed
                "sequence_id": seq.id,
                "lead_id": lead_id,
                "reason": "score_threshold",
            },
            entity_type="lead",
            entity_id=lead_id,
        )

    return enrolled_in


def _lead_matches_auto_rules(lead, rules: list[dict]) -> bool:
    """Check if a lead matches auto-enrollment rules.

    Rules can include score thresholds, status checks, field checks, etc.
    Format: [{"field": "lead_score", "op": "gte", "value": 70}, ...]
    """
    for rule in rules:
        field = rule.get("field", "")
        op = rule.get("op", "")
        value = rule.get("value", "")

        if not hasattr(lead, field):
            continue

        field_val = getattr(lead, field)

        if op == "gte":
            try:
                if float(field_val or 0) < float(value):
                    return False
            except (TypeError, ValueError):
                return False
        elif op == "lte":
            try:
                if float(field_val or 0) > float(value):
                    return False
            except (TypeError, ValueError):
                return False
        elif op == "equals":
            if str(field_val) != str(value):
                return False
        elif op == "contains":
            if value.lower() not in str(field_val or "").lower():
                return False
        elif op == "not_empty":
            if not field_val:
                return False

    return True
