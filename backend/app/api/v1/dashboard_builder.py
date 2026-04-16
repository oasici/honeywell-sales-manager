"""Dashboard builder endpoints — user-customizable widget-based dashboards."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import ForbiddenException, NotFoundException
from app.models.dashboard_config import DashboardConfig
from app.models.report import ReportTemplate
from app.models.user import User
from app.services.report_engine import ReportEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboards", tags=["Dashboard Builder"])


def _check_feature_flag() -> None:
    if not settings.FEATURE_DASHBOARD_BUILDER:
        raise ForbiddenException("Dashboard olusturucu ozelligi su anda devre disi")


# -- Schemas --


class DashboardCreate(BaseModel):
    name: str = Field(max_length=200, min_length=1)
    widgets_json: str
    is_default: bool = False


class DashboardUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    widgets_json: str | None = None
    is_default: bool | None = None


# -- Endpoints --


@router.get("/")
async def list_dashboards(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's dashboards."""
    _check_feature_flag()

    result = await db.execute(
        select(DashboardConfig)
        .where(DashboardConfig.owner_id == current_user.id)
        .order_by(DashboardConfig.created_at.desc())
    )
    dashboards = result.scalars().all()

    return {
        "data": [
            {
                "id": d.id,
                "name": d.name,
                "widgets_json": d.widgets_json,
                "is_default": d.is_default,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in dashboards
        ],
    }


@router.post("/", status_code=201)
async def create_dashboard(
    body: DashboardCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new dashboard."""
    _check_feature_flag()
    _validate_widgets_json(body.widgets_json)

    # If setting as default, unset other defaults
    if body.is_default:
        await _unset_default_dashboards(db, current_user.id)

    dashboard = DashboardConfig(
        name=body.name,
        owner_id=current_user.id,
        widgets_json=body.widgets_json,
        is_default=body.is_default,
    )
    db.add(dashboard)
    await db.flush()
    await db.refresh(dashboard)

    return {
        "data": {
            "id": dashboard.id,
            "name": dashboard.name,
            "widgets_json": dashboard.widgets_json,
            "is_default": dashboard.is_default,
            "created_at": dashboard.created_at.isoformat() if dashboard.created_at else None,
        },
    }


@router.put("/{dashboard_id}")
async def update_dashboard(
    dashboard_id: int,
    body: DashboardUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update dashboard widgets or settings."""
    _check_feature_flag()

    dashboard = await _get_user_dashboard(db, dashboard_id, current_user)

    if body.widgets_json is not None:
        _validate_widgets_json(body.widgets_json)

    if body.is_default:
        await _unset_default_dashboards(db, current_user.id)

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(dashboard, key, value)

    await db.flush()
    await db.refresh(dashboard)

    return {
        "data": {
            "id": dashboard.id,
            "name": dashboard.name,
            "widgets_json": dashboard.widgets_json,
            "is_default": dashboard.is_default,
        },
    }


@router.delete("/{dashboard_id}", status_code=204)
async def delete_dashboard(
    dashboard_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a dashboard."""
    _check_feature_flag()

    dashboard = await _get_user_dashboard(db, dashboard_id, current_user)
    await db.delete(dashboard)


@router.get("/{dashboard_id}/execute")
async def execute_dashboard(
    dashboard_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute all widget reports and return data."""
    _check_feature_flag()

    dashboard = await _get_user_dashboard(db, dashboard_id, current_user)

    try:
        widgets = json.loads(dashboard.widgets_json)
    except json.JSONDecodeError:
        return {"data": {"id": dashboard.id, "name": dashboard.name, "widgets": []}}

    engine = ReportEngine(db)
    widget_results = []

    for widget in widgets:
        widget_data = {
            "type": widget.get("type", "unknown"),
            "position": widget.get("position", {}),
            "report_id": widget.get("report_id"),
            "data": None,
            "error": None,
        }

        report_id = widget.get("report_id")
        if report_id:
            try:
                result = await engine.execute_report(report_id, limit=100, offset=0)
                widget_data["data"] = result
            except Exception as exc:
                widget_data["error"] = f"Rapor calistirilamadi: {exc}"

        widget_results.append(widget_data)

    return {
        "data": {
            "id": dashboard.id,
            "name": dashboard.name,
            "widgets": widget_results,
        },
    }


# -- Helpers --


async def _get_user_dashboard(
    db: AsyncSession, dashboard_id: int, current_user: User
) -> DashboardConfig:
    """Get a dashboard, verifying ownership."""
    result = await db.execute(
        select(DashboardConfig).where(DashboardConfig.id == dashboard_id)
    )
    dashboard = result.scalar_one_or_none()
    if dashboard is None:
        raise NotFoundException("Dashboard bulunamadi")

    if dashboard.owner_id != current_user.id:
        raise ForbiddenException("Bu dashboard'a erisim yetkiniz yok")

    return dashboard


async def _unset_default_dashboards(db: AsyncSession, owner_id: int) -> None:
    """Unset is_default on all dashboards for a user."""
    result = await db.execute(
        select(DashboardConfig).where(
            DashboardConfig.owner_id == owner_id,
            DashboardConfig.is_default.is_(True),
        )
    )
    for d in result.scalars().all():
        d.is_default = False


def _validate_widgets_json(widgets_json: str) -> None:
    """Validate widgets JSON structure."""
    try:
        widgets = json.loads(widgets_json)
    except json.JSONDecodeError:
        raise ForbiddenException("widgets_json gecerli bir JSON dizisi olmali")

    if not isinstance(widgets, list):
        raise ForbiddenException("widgets_json bir liste olmali")
