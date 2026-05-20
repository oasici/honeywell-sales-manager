"""Signature response schemas — typed surfaces for /signatures/*."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SignatureRequestResponse(BaseModel):
    id: int | None = None
    tenant_id: int | None = None
    document_type: str | None = None
    document_id: int | None = None
    signer_email: str | None = None
    signer_name: str | None = None
    status: str | None = None
    token: str | None = None
    signed_at: str | None = None
    viewed_at: str | None = None
    expires_at: str | None = None
    ip_address: str | None = None
    created_by: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class SignatureRequestListResponse(BaseModel):
    items: list[SignatureRequestResponse] = []
    total: int | None = None
    skip: int | None = None
    limit: int | None = None

    model_config = {"extra": "allow"}


class SignatureRequestCreatedResponse(BaseModel):
    message: str | None = None
    id: int | None = None
    token: str | None = None
    signer_email: str | None = None
    expires_at: str | None = None

    model_config = {"extra": "allow"}


class SignaturePublicPageResponse(BaseModel):
    id: int | None = None
    document_type: str | None = None
    document_id: int | None = None
    signer_email: str | None = None
    signer_name: str | None = None
    status: str | None = None
    expires_at: str | None = None
    document: dict[str, Any] | None = None

    model_config = {"extra": "allow"}


class SignatureSubmitResponse(BaseModel):
    message: str | None = None
    id: int | None = None
    signed_at: str | None = None

    model_config = {"extra": "allow"}


class SignatureSimpleResponse(BaseModel):
    """Used by cancel/decline endpoints that return ``{message, id}``."""

    message: str | None = None
    id: int | None = None

    model_config = {"extra": "allow"}
