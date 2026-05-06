from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: str = Field(default="sales_rep", pattern=r"^(sales_rep|sales_manager|operations)$")


class UserResponse(BaseModel):
    """Auth-flow user surface.

    R5-API-2 / R5-TS-4 — adds tenant_id and manager_id so the SPA's
    /auth/me + /auth/login responses carry the same identity surface
    as /api/v1/users/* (and so the auth store can populate org-chart
    UI without a second round-trip).
    """

    id: int
    tenant_id: int | None = None
    manager_id: int | None = None
    email: str
    full_name: str
    role: str
    is_active: bool
    email_setup_completed: bool = False
    password_change_required: bool = False
    created_at: datetime
    # R6-DB-3 — model declares ``updated_at`` as non-null Mapped[datetime];
    # schema drifted to Optional, leading codegen consumers to handle a
    # null state that never occurs.
    updated_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    password_change_required: bool = False
    user: UserResponse
