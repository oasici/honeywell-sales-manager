"""Feature-11: Saved views / filters per user."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.saved_view import SavedView
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.shared_document import SavedViewResponse

router = APIRouter(prefix="/saved-views", tags=["Saved Views"])


class SavedViewCreate(BaseModel):
    name: str
    route: str
    query_json: str = "{}"


@router.get("/", response_model=PaginatedResponse[SavedViewResponse])
async def list_saved_views(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List current user's saved views.

    Round-13 R13-API-1 → Sprint 7b — legacy ``views`` alias dropped.
    PlanningStudioPage and SavedViewsBar both read ``items`` first
    (R13 Sprint 1b migration), making the alias dead weight.
    """
    # Round-11 R11-AUTH-4 — tenant scope alongside user_id.
    conditions = [SavedView.user_id == current_user.id]
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is not None:
        conditions.append(SavedView.tenant_id == tenant_id)
    result = await db.execute(
        select(SavedView).where(*conditions).order_by(SavedView.created_at.desc())
    )
    views = result.scalars().all()
    items = [
        {
            "id": v.id,
            "name": v.name,
            "route": v.route,
            "query_json": v.query_json,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in views
    ]
    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": len(items) if items else 0,
        "pages": 1 if items else 0,
    }


@router.post("/", status_code=201, response_model=SavedViewResponse)
async def create_saved_view(
    body: SavedViewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a new view/filter."""
    view = SavedView(
        user_id=current_user.id,
        # Round-11 R11-AUTH-4 — persist caller tenant on insert so the
        # delete/list paths can filter on it.
        tenant_id=getattr(current_user, "tenant_id", None),
        name=body.name,
        route=body.route,
        query_json=body.query_json,
    )
    db.add(view)
    await db.flush()
    await db.refresh(view)
    return {
        "id": view.id,
        "name": view.name,
        "route": view.route,
        "query_json": view.query_json,
        "created_at": view.created_at.isoformat() if view.created_at else None,
    }


@router.delete("/{view_id}", status_code=200, response_model=dict)
async def delete_saved_view(
    view_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a saved view (own only).

    Round-11 R11-AUTH-4 — additionally scope by ``tenant_id`` so that a
    user_id collision across tenants cannot delete foreign-tenant views.
    Missing/foreign-tenant views return 404 (never 403) to avoid leaking
    existence per the project convention.
    """
    conditions = [SavedView.id == view_id, SavedView.user_id == current_user.id]
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is not None:
        conditions.append(SavedView.tenant_id == tenant_id)
    result = await db.execute(select(SavedView).where(*conditions))
    view = result.scalar_one_or_none()
    if not view:
        raise NotFoundException("Gorunum bulunamadi")
    await db.delete(view)
    await db.flush()
    return {"message": "Gorunum silindi"}
