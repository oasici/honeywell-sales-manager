"""Chat (live chat) response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ChatSessionResponse(BaseModel):
    id: int | None = None
    tenant_id: int | None = None
    visitor_id: str | None = None
    assigned_agent_id: int | None = None
    status: str | None = None
    metadata_json: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class ChatMessageResponse(BaseModel):
    id: int | None = None
    tenant_id: int | None = None
    session_id: int | None = None
    sender_type: str | None = None
    sender_id: str | None = None
    content: str | None = None
    message_type: str | None = None
    is_read: bool | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class ChatMessageSendResponse(BaseModel):
    """`/chat/sessions/{id}/messages` POST response — always returns ``message``,
    optionally ``auto_response`` when a rule fires.
    """

    message: ChatMessageResponse | dict[str, Any] | None = None
    auto_response: ChatMessageResponse | dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class AutoResponseRuleResponse(BaseModel):
    id: int | None = None
    tenant_id: int | None = None
    trigger_keyword: str | None = None
    response_text: str | None = None
    is_active: bool | None = None
    priority: int | None = None
    created_by: int | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
