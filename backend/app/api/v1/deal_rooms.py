"""Deal Room / Buyer Collaboration API endpoints."""

from __future__ import annotations

import json
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.deal_room import DealRoom
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.tenant_context import assert_same_tenant


async def _assert_opp_in_tenant(
    db: AsyncSession, current_user: User, opportunity_id: int
) -> None:
    """R5-TEN-26 — DealRoom carries opportunity_id but no tenant_id of
    its own. Load the parent opportunity and assert tenant match.
    Both 'doesn't exist' and 'cross-tenant' collapse to 404."""
    opp = (
        await db.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
    ).scalar_one_or_none()
    if opp is None:
        raise NotFoundException("Firsat bulunamadi")
    assert_same_tenant(opp, current_user, exception_cls=NotFoundException)

router = APIRouter(tags=["Deal Rooms"])

TOKEN_LENGTH = 32


class DealRoomCreate(BaseModel):
    opportunity_id: int
    name: str = Field(..., max_length=200)
    welcome_message: str | None = None


class DealRoomUpdate(BaseModel):
    shared_items_json: str | None = None
    mutual_action_plan_json: str | None = None
    welcome_message: str | None = None


class BuyerActionBody(BaseModel):
    item_index: int
    completed: bool


def _serialize(room: DealRoom) -> dict:
    """Convert a DealRoom ORM instance to a JSON-friendly dict."""
    return {
        "id": room.id,
        "opportunity_id": room.opportunity_id,
        "name": room.name,
        "external_token": room.external_token,
        "shared_items_json": room.shared_items_json,
        "mutual_action_plan_json": room.mutual_action_plan_json,
        "welcome_message": room.welcome_message,
        "is_active": room.is_active,
        "last_buyer_activity_at": (
            room.last_buyer_activity_at.isoformat()
            if room.last_buyer_activity_at
            else None
        ),
        "created_by": room.created_by,
        "created_at": room.created_at.isoformat() if room.created_at else None,
    }


# ── Internal (auth required) ────────────────────────────


@router.get("/deal-rooms/")
async def list_deal_rooms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List deal rooms created by the current user."""
    stmt = (
        select(DealRoom)
        .where(DealRoom.created_by == current_user.id, DealRoom.is_active.is_(True))
        .order_by(DealRoom.created_at.desc())
    )
    result = await db.execute(stmt)
    rooms = result.scalars().all()
    # R6-PAGE-1 — canonical envelope.
    items = [_serialize(r) for r in rooms]
    total = len(items)
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
    }


@router.post("/deal-rooms/", status_code=201)
async def create_deal_room(
    body: DealRoomCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new deal room with auto-generated external token."""
    # R5-TEN-26 — block cross-tenant deal-room hangs.
    await _assert_opp_in_tenant(db, current_user, body.opportunity_id)
    token = secrets.token_hex(TOKEN_LENGTH)
    room = DealRoom(
        opportunity_id=body.opportunity_id,
        name=body.name,
        welcome_message=body.welcome_message,
        external_token=token,
        created_by=current_user.id,
    )
    db.add(room)
    await db.flush()
    return _serialize(room)


@router.get("/deal-rooms/{room_id}")
async def get_deal_room(
    room_id: int,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get deal room detail."""
    result = await db.execute(select(DealRoom).where(DealRoom.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Deal room bulunamadi")
    await _assert_opp_in_tenant(db, _current_user, room.opportunity_id)
    return _serialize(room)


@router.put("/deal-rooms/{room_id}")
async def update_deal_room(
    room_id: int,
    body: DealRoomUpdate,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update shared items, action plan, or welcome message."""
    result = await db.execute(select(DealRoom).where(DealRoom.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Deal room bulunamadi")
    await _assert_opp_in_tenant(db, _current_user, room.opportunity_id)

    if body.shared_items_json is not None:
        room.shared_items_json = body.shared_items_json
    if body.mutual_action_plan_json is not None:
        room.mutual_action_plan_json = body.mutual_action_plan_json
    if body.welcome_message is not None:
        room.welcome_message = body.welcome_message

    await db.flush()
    return _serialize(room)


@router.delete("/deal-rooms/{room_id}")
async def deactivate_deal_room(
    room_id: int,
    _current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-deactivate a deal room."""
    result = await db.execute(select(DealRoom).where(DealRoom.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Deal room bulunamadi")
    await _assert_opp_in_tenant(db, _current_user, room.opportunity_id)

    room.is_active = False
    await db.flush()
    return {"message": "Deal room devre disi birakildi"}


# ── Public (no auth) ────────────────────────────────────


@router.get("/deal-rooms/public/{token}")
async def get_public_deal_room(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Buyer-facing view. Updates last_buyer_activity_at."""
    result = await db.execute(
        select(DealRoom).where(
            DealRoom.external_token == token,
            DealRoom.is_active.is_(True),
        )
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Deal room bulunamadi veya aktif degil")

    room.last_buyer_activity_at = datetime.now(timezone.utc)
    await db.flush()
    return _serialize(room)


@router.post("/deal-rooms/public/{token}/action")
async def buyer_action(
    token: str,
    body: BuyerActionBody,
    db: AsyncSession = Depends(get_db),
):
    """Buyer marks an action item as complete/incomplete."""
    result = await db.execute(
        select(DealRoom).where(
            DealRoom.external_token == token,
            DealRoom.is_active.is_(True),
        )
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Deal room bulunamadi veya aktif degil")

    # Parse existing action plan
    plan: list[dict] = []
    if room.mutual_action_plan_json:
        try:
            plan = json.loads(room.mutual_action_plan_json)
        except (json.JSONDecodeError, TypeError):
            raise HTTPException(status_code=422, detail="Aksiyon plani ayristirilamadi")

    if body.item_index < 0 or body.item_index >= len(plan):
        raise HTTPException(status_code=422, detail="Gecersiz madde indeksi")

    plan[body.item_index]["completed"] = body.completed
    room.mutual_action_plan_json = json.dumps(plan)
    room.last_buyer_activity_at = datetime.now(timezone.utc)
    await db.flush()
    return {"message": "Aksiyon guncellendi", "plan": plan}
