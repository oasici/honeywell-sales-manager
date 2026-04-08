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

router = APIRouter(prefix="/saved-views", tags=["Saved Views"])


class SavedViewCreate(BaseModel):
    name: str
    route: str
    query_json: str = "{}"


@router.get("/")
async def list_saved_views(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List current user's saved views."""
    result = await db.execute(
        select(SavedView)
        .where(SavedView.user_id == current_user.id)
        .order_by(SavedView.created_at.desc())
    )
    views = result.scalars().all()
    return {
        "views": [
            {
                "id": v.id,
                "name": v.name,
                "route": v.route,
                "query_json": v.query_json,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in views
        ]
    }


@router.post("/", status_code=201)
async def create_saved_view(
    body: SavedViewCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Save a new view/filter."""
    view = SavedView(
        user_id=current_user.id,
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


@router.delete("/{view_id}", status_code=200)
async def delete_saved_view(
    view_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a saved view (own only)."""
    result = await db.execute(
        select(SavedView).where(SavedView.id == view_id, SavedView.user_id == current_user.id)
    )
    view = result.scalar_one_or_none()
    if not view:
        raise NotFoundException("Gorunum bulunamadi")
    await db.delete(view)
    await db.flush()
    return {"message": "Gorunum silindi"}
