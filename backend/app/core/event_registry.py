from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActivityDefinition:
    activity_type: str
    entity_type: str
    opportunity_event_type: str


# Authoritative registry for V1 activity_logs.activity_type values.
# Keep this list tight: add only when there is a real producer and a consumer.
ACTIVITY_REGISTRY: dict[str, ActivityDefinition] = {
    # Emails
    "email_received": ActivityDefinition("email_received", "email", "email"),
    "email_parsed": ActivityDefinition("email_parsed", "email", "email"),
    # Quotes
    "quote_created": ActivityDefinition("quote_created", "quote", "quote"),
    "quote_approved": ActivityDefinition("quote_approved", "quote", "quote"),
    "quote_sent": ActivityDefinition("quote_sent", "quote", "quote"),
    # Opportunity lifecycle
    "stage_change": ActivityDefinition("stage_change", "opportunity", "stage_change"),
    # Tasks
    "task_created": ActivityDefinition("task_created", "task", "task"),
    "task_completed": ActivityDefinition("task_completed", "task", "task"),
    # Meetings / calendar
    "meeting_booked": ActivityDefinition("meeting_booked", "meeting", "meeting"),
    "calendar_stub": ActivityDefinition("calendar_stub", "meeting", "meeting"),
    # Notes / misc
    "note_added": ActivityDefinition("note_added", "opportunity", "note"),
    "transcript_uploaded": ActivityDefinition("transcript_uploaded", "transcript", "meeting"),
    # Ops / admin
    "merge_customer": ActivityDefinition("merge_customer", "customer", "note"),
}


def is_known_activity_type(activity_type: str) -> bool:
    return activity_type in ACTIVITY_REGISTRY


def opportunity_event_type_for(activity_type: str) -> str:
    """Map activity_logs.activity_type to opportunity_events.event_type."""
    if activity_type in ACTIVITY_REGISTRY:
        return ACTIVITY_REGISTRY[activity_type].opportunity_event_type
    # Fail-open: preserve data even if registry missed a new type.
    return activity_type


def validate_activity_entity(activity_type: str, entity_type: str) -> bool:
    """Return True if entity_type matches registry (or activity is unknown)."""
    if activity_type not in ACTIVITY_REGISTRY:
        return True
    return ACTIVITY_REGISTRY[activity_type].entity_type == entity_type

