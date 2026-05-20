"""Sequence response schema.

Round-13 Sprint 6b — see ``invoice.py`` for the design pattern.
Round-15 F-009 — added ``SequenceResponseParsed`` for the parsed wire
format. ``SequenceResponse`` keeps the raw-JSON shape (Pydantic emits
the columns as-stored); the parsed variant is what the API endpoints
actually return after ``_sequence_to_dict`` parses
``steps_json`` / ``auto_enroll_rules_json``. The SPA migrated to the
parsed type in 15m-6.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SequenceResponse(BaseModel):
    id: int
    tenant_id: int | None = None
    name: str | None = None
    description: str | None = None
    steps_json: str | None = None
    auto_enroll_rules_json: str | None = None
    exit_criteria_json: str | None = None
    is_active: bool | None = None
    created_by: int | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class SequenceResponseParsed(BaseModel):
    """Sequence with JSON fields pre-parsed server-side.

    Returned by:
      * ``GET /sequences/`` (list — minus ``auto_enroll_rules``)
      * ``GET /sequences/{id}`` (detail — full)
    """

    id: int
    tenant_id: int | None = None
    name: str | None = None
    description: str | None = None
    # ``steps`` is the parsed form of ``steps_json``. Each step is a
    # free-shape dict (action_type, delay_days, payload_json, etc.).
    steps: list[dict[str, Any]] = []
    # ``auto_enroll_rules`` parsed from ``auto_enroll_rules_json``. The
    # list endpoint omits this; detail returns it. The wire format
    # accepts either a list (rule array) or a dict (single rule).
    auto_enroll_rules: list[Any] | dict[str, Any] | None = None
    is_active: bool | None = None
    created_by: int | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
