"""Email template response schema.

Round-13 Sprint 6b — see ``invoice.py`` for the design pattern.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class EmailTemplateResponse(BaseModel):
    id: int
    tenant_id: int | None = None
    name: str | None = None
    subject: str | None = None
    body_html: str | None = None
    variables_json: str | None = None
    category: str | None = None
    is_shared: bool | None = None
    created_by: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
