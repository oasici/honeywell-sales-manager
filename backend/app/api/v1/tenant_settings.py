"""F-029 wire — per-tenant settings endpoint.

    GET    /admin/tenant-settings    — current settings (or defaults)
    PUT    /admin/tenant-settings    — update (ops-only)

Currently surfaces the F-029 ``auto_quote_max_amount`` cap that the
email eligibility gate checks. Future Phase 5 settings (base
currency, OCR cap override, AI monthly quota) plug onto the same
row + schema with no API shape change.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.tenant_settings_service import get_tenant_settings


router = APIRouter(prefix="/admin/tenant-settings", tags=["Tenant Settings"])


class TenantSettingsView(BaseModel):
    tenant_id: int
    auto_quote_max_amount: Optional[Decimal]
    auto_quote_currency: str
    base_currency: str
    ocr_max_pages: int
    ai_monthly_quota_usd: Optional[Decimal]


class TenantSettingsUpdate(BaseModel):
    auto_quote_max_amount: Optional[Decimal] = Field(default=None, ge=0)
    auto_quote_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    base_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    ocr_max_pages: Optional[int] = Field(default=None, ge=1, le=100)
    ai_monthly_quota_usd: Optional[Decimal] = Field(default=None, ge=0)


def _require_ops(user: User) -> None:
    role = getattr(user, "role", None)
    if role not in {
        "operations", "ops_users", "ops_data", "ops_billing",
    }:
        raise HTTPException(403, detail="tenant_settings_requires_ops")


@router.get("", response_model=TenantSettingsView)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantSettingsView:
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(400, detail="user_has_no_tenant")
    cfg = await get_tenant_settings(db, tenant_id)
    return TenantSettingsView(**cfg.__dict__)


@router.put("", response_model=TenantSettingsView)
async def update_settings(
    payload: TenantSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TenantSettingsView:
    _require_ops(current_user)
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(400, detail="user_has_no_tenant")

    # UPSERT so first-time configuration creates the row.
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        return await get_settings(current_user=current_user, db=db)

    # Build the SET clause safely (whitelisted keys).
    allowed = {
        "auto_quote_max_amount",
        "auto_quote_currency",
        "base_currency",
        "ocr_max_pages",
        "ai_monthly_quota_usd",
    }
    bad = set(updates.keys()) - allowed
    if bad:
        raise HTTPException(400, detail={"unknown_keys": sorted(bad)})

    set_clause = ", ".join(f"{k} = :{k}" for k in updates.keys())
    update_clause = ", ".join(f"{k} = EXCLUDED.{k}" for k in updates.keys())
    sql = text(
        f"""
        INSERT INTO tenant_settings (tenant_id, {", ".join(updates.keys())})
        VALUES (:tenant_id, {", ".join(":" + k for k in updates.keys())})
        ON CONFLICT (tenant_id) DO UPDATE SET {update_clause}, updated_at = now()
        """
    )
    params = {**updates, "tenant_id": tenant_id}
    await db.execute(sql, params)
    await db.flush()
    return await get_settings(current_user=current_user, db=db)
