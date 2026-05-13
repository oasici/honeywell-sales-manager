"""Shared document response schema.

Round-13 Sprint 7b — see ``invoice.py`` for the design pattern.
"""

from __future__ import annotations

from pydantic import BaseModel


class SharedDocumentResponse(BaseModel):
    id: int
    quote_id: int | None = None
    file_name: str | None = None
    file_url: str | None = None
    shared_with_email: str | None = None
    tracking_token: str | None = None
    views_count: int | None = None
    first_viewed_at: str | None = None
    last_viewed_at: str | None = None
    total_view_seconds: float | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class SavedViewResponse(BaseModel):
    """Saved board / list view shape.

    Round-13 Sprint 7b — promote saved_views from PaginatedResponse[dict]
    to a typed per-item shape. Used by PlanningStudioPage + SavedViewsBar.
    """

    id: int
    name: str | None = None
    route: str | None = None
    query_json: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
