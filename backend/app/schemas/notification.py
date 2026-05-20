"""Notification API response shapes.

Round-15 N15-API-1 quick-win 4 — pre-Round-15 ``/notifications/`` was
typed as ``PaginatedResponse[dict]``. ``get_notifications`` already
returns a fixed 8-field shape; declaring this schema lets OpenAPI /
``api-types.gen.ts`` consumers stop falling back to ``unknown``.
"""

from __future__ import annotations

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    """Wire shape for a single notification row.

    Mirrors ``backend/app/services/notification_service.py::get_notifications``
    (the bell-icon header + notifications page consume this). The
    backing column on ``notifications`` is ``created_at`` (TIMESTAMPTZ);
    the service emits it as an ISO string, so the schema reflects the
    wire format rather than coercing back to ``datetime`` only to
    re-serialise.
    """

    id: int
    type: str
    title: str
    message: str | None = None
    is_read: bool
    entity_type: str | None = None
    entity_id: int | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True}
