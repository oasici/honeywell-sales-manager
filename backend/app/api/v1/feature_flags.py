"""Feature-flag admin REST surface (SALES_MANAGER only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.enums import UserRole
from app.models.user import User
from app.services import feature_flags as ff_service

router = APIRouter(prefix="/admin/feature-flags", tags=["Feature Flags"])


class FeatureFlagRow(BaseModel):
    name: str
    default: bool
    env_value: bool
    override: bool | None
    effective: bool
    description: str = ""


class FeatureFlagPatch(BaseModel):
    # Tri-state: true/false set an override; null clears it (revert to env).
    enabled: bool | None = Field(
        None, description="null clears the override and reverts to env"
    )


@router.get("", response_model=list[FeatureFlagRow])
async def list_feature_flags(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await ff_service.list_flags(db)


@router.patch("/{flag_name}", response_model=FeatureFlagRow)
async def patch_feature_flag(
    flag_name: str,
    body: FeatureFlagPatch,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await ff_service.set_override(db, name=flag_name, enabled=body.enabled)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()

    rows = await ff_service.list_flags(db)
    for row in rows:
        if row["name"] == flag_name:
            return row
    raise HTTPException(500, "Flag not found after patch")


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, response_class=None)
async def clear_all_overrides(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
):
    await ff_service.clear_overrides(db)
    await db.commit()
