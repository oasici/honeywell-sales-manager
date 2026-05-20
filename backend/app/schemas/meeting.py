"""Meeting response schemas — typed surfaces for /meetings/*."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class MeetingLinkResponse(BaseModel):
    id: int | None = None
    slug: str | None = None
    title: str | None = None
    duration_minutes: int | None = None
    is_active: bool | None = None
    booking_url: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class MeetingLinkEnvelope(BaseModel):
    """{ data: MeetingLinkResponse } wrapper used by list/create endpoints."""

    data: MeetingLinkResponse | list[MeetingLinkResponse] | dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class MeetingLinkListResponse(BaseModel):
    data: list[MeetingLinkResponse] = []

    model_config = {"extra": "allow"}


class MeetingBookingResponse(BaseModel):
    id: int | None = None
    meeting_link_id: int | None = None
    booker_name: str | None = None
    booker_email: str | None = None
    scheduled_at: str | None = None
    notes: str | None = None
    status: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class MeetingBookingListResponse(BaseModel):
    data: list[MeetingBookingResponse] = []

    model_config = {"extra": "allow"}


class MeetingBookingCreateResponse(BaseModel):
    data: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class MeetingBookingPagePublicResponse(BaseModel):
    data: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class MeetingPlaceholderResponse(BaseModel):
    data: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class MeetingMessageResponse(BaseModel):
    """{ data: { message: str } } for deactivate-link, etc."""

    data: dict[str, Any] | None = None

    model_config = {"extra": "allow"}
