"""Activity log response shapes.

Round-15 N15-API-1 — close ``PaginatedResponse[dict]`` holdouts on
``/api/v1/activities/`` + ``/api/v1/activities/feed``. Mirrors
``api/v1/activities.py::_serialize_activity`` exactly.
"""

from __future__ import annotations

from pydantic import BaseModel


class ActivityResponse(BaseModel):
    id: int
    activity_type: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    opportunity_id: int | None = None
    customer_id: int | None = None
    user_id: int | None = None
    summary: str | None = None
    duration_minutes: int | None = None
    outcome: str | None = None
    attendees_json: str | None = None
    agenda: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
