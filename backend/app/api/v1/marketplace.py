"""Marketplace / plugin REST surface."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.enums import UserRole
from app.models.marketplace import (
    Plugin,
    PluginEventSubscription,
    PluginInstallation,
)
from app.models.user import User
from app.services.marketplace import (
    MarketplaceError,
    ScopeDenied,
    add_subscription,
    install_plugin,
    uninstall_plugin,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/marketplace", tags=["Marketplace"])


def _require_flag() -> None:
    if not settings.FEATURE_MARKETPLACE:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marketplace disabled")


# ── Plugin catalogue ────────────────────────────────────────────────────────


class PluginCreate(BaseModel):
    slug: str = Field(..., min_length=3, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    publisher: str = "first_party"
    version: str = "1.0.0"
    description: str | None = None
    homepage_url: str | None = None
    icon_url: str | None = None
    scopes: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    is_public: bool = True


class PluginOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    publisher: str
    version: str
    description: str | None
    homepage_url: str | None
    icon_url: str | None
    scopes_json: str
    events_json: str
    is_public: bool
    is_active: bool
    created_at: datetime


@router.get("/plugins", response_model=list[PluginOut])
async def list_plugins(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS, UserRole.SALES_REP))],
    db: AsyncSession = Depends(get_db),
) -> list[Plugin]:
    _require_flag()
    rows = (
        await db.execute(
            select(Plugin).where(Plugin.is_active.is_(True)).order_by(Plugin.name)
        )
    ).scalars().all()
    return list(rows)


@router.post("/plugins", response_model=PluginOut, status_code=status.HTTP_201_CREATED)
async def create_plugin(
    body: PluginCreate,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
) -> Plugin:
    _require_flag()
    existing = (
        await db.execute(select(Plugin).where(Plugin.slug == body.slug))
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "Plugin slug already exists")
    row = Plugin(
        slug=body.slug,
        name=body.name,
        publisher=body.publisher,
        version=body.version,
        description=body.description,
        homepage_url=body.homepage_url,
        icon_url=body.icon_url,
        scopes_json=json.dumps(body.scopes, ensure_ascii=False),
        events_json=json.dumps(body.events, ensure_ascii=False),
        is_public=body.is_public,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


# ── Installations ───────────────────────────────────────────────────────────


class InstallRequest(BaseModel):
    plugin_slug: str
    granted_scopes: list[str] = Field(default_factory=list)
    config: dict[str, Any] | None = None


class InstallationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plugin_id: int
    tenant_id: int
    status: str
    granted_scopes_json: str
    config_json: str | None
    installed_at: datetime
    uninstalled_at: datetime | None


class InstallResult(BaseModel):
    installation: InstallationOut
    api_token: str = Field(..., description="Shown once; store securely.")


@router.post("/installations", response_model=InstallResult, status_code=status.HTTP_201_CREATED)
async def install(
    body: InstallRequest,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
) -> InstallResult:
    _require_flag()
    try:
        installation, token = await install_plugin(
            db,
            plugin_slug=body.plugin_slug,
            granted_scopes=body.granted_scopes,
            installed_by=current_user.id,
            config=body.config,
        )
    except ScopeDenied as exc:
        raise HTTPException(403, str(exc)) from exc
    except MarketplaceError as exc:
        raise HTTPException(400, str(exc)) from exc

    await db.commit()
    return InstallResult(
        installation=InstallationOut.model_validate(installation), api_token=token
    )


@router.get("/installations", response_model=list[InstallationOut])
async def list_installations(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    db: AsyncSession = Depends(get_db),
) -> list[PluginInstallation]:
    _require_flag()
    rows = (
        await db.execute(
            select(PluginInstallation)
            .where(PluginInstallation.status == "active")
            .order_by(PluginInstallation.installed_at.desc())
        )
    ).scalars().all()
    return list(rows)


@router.delete("/installations/{installation_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=None)
async def uninstall(
    installation_id: int,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
):
    _require_flag()
    try:
        await uninstall_plugin(db, installation_id=installation_id)
    except MarketplaceError as exc:
        raise HTTPException(404, str(exc)) from exc
    await db.commit()


# ── Subscriptions ──────────────────────────────────────────────────────────


class SubscriptionCreate(BaseModel):
    installation_id: int
    event_type: str = Field(..., min_length=1, max_length=80)
    target_url: str = Field(..., min_length=8, max_length=500)
    secret: str | None = None


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    installation_id: int
    event_type: str
    target_url: str
    is_active: bool
    created_at: datetime


@router.post("/subscriptions", response_model=SubscriptionOut, status_code=status.HTTP_201_CREATED)
async def create_subscription(
    body: SubscriptionCreate,
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
    db: AsyncSession = Depends(get_db),
) -> PluginEventSubscription:
    _require_flag()
    installation = await db.get(PluginInstallation, body.installation_id)
    if not installation or installation.status != "active":
        raise HTTPException(404, "Active installation not found")
    try:
        row = await add_subscription(
            db,
            installation=installation,
            event_type=body.event_type,
            target_url=body.target_url,
            secret=body.secret,
        )
    except ScopeDenied as exc:
        raise HTTPException(403, str(exc)) from exc

    await db.commit()
    await db.refresh(row)
    return row


@router.get("/subscriptions", response_model=list[SubscriptionOut])
async def list_subscriptions(
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS))],
    installation_id: int | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[PluginEventSubscription]:
    _require_flag()
    stmt = select(PluginEventSubscription)
    if installation_id is not None:
        stmt = stmt.where(PluginEventSubscription.installation_id == installation_id)
    rows = (await db.execute(stmt.order_by(PluginEventSubscription.created_at.desc()))).scalars().all()
    return list(rows)
