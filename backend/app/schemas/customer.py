from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    tax_id: str | None = Field(default=None, max_length=50)
    preferred_lang: str = Field(default="tr", max_length=5)


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    company: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = None
    tax_id: str | None = Field(default=None, max_length=50)
    preferred_lang: str | None = Field(default=None, max_length=5)


class CustomerResponse(BaseModel):
    id: int
    name: str
    company: str | None = None
    email: str
    phone: str | None = None
    address: str | None = None
    tax_id: str | None = None
    preferred_lang: str
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime

    quote_count: int | None = None
    total_quote_value: float | None = None

    model_config = {"from_attributes": True}
