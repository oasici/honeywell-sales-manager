from __future__ import annotations

import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.deal_replay_snapshot import DealReplaySnapshot
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.deal_replay_snapshot_service import materialize_deal_replay_snapshot
from app.schemas.common import ItemsResponse
from app.schemas.round16_aggregates import (
    DealReplayFramesResponse,
    DealReplayMaterializeResponse,
)

router = APIRouter(prefix="/v4/replay", tags=["V4 Deal Replay"])


def _require_deal_replay():
    if not settings.FEATURE_V4_DEAL_REPLAY:
        raise HTTPException(status_code=404, detail="Not found")


async def _ensure_opp_access(
    db: AsyncSession, opportunity_id: int, current_user: User
) -> Opportunity:
    # V13 cross-tenant guard before RBAC
    from app.core.exceptions import NotFoundException
    from app.services.tenant_context import load_with_tenant_check

    try:
        opp = await load_with_tenant_check(
            db,
            Opportunity,
            opportunity_id,
            current_user=current_user,
            exception_cls=NotFoundException,
            message="Fırsat bulunamadı",
        )
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Fırsat bulunamadı")
    if current_user.role == UserRole.SALES_REP.value and int(opp.owner_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Yetkisiz")
    return opp


@router.get("/opportunities/{opportunity_id}/snapshots", response_model=ItemsResponse)
async def list_replay_snapshots(
    opportunity_id: int,
    limit: int = Query(60, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_deal_replay),
):
    await _ensure_opp_access(db, opportunity_id, current_user)
    rows = (
        await db.execute(
            select(DealReplaySnapshot)
            .where(DealReplaySnapshot.opportunity_id == opportunity_id)
            .order_by(DealReplaySnapshot.snapshot_date.desc())
            .limit(limit)
        )
    ).scalars().all()

    items = []
    for r in rows:
        try:
            meta = json.loads(r.meta_json or "{}")
        except json.JSONDecodeError:
            meta = {}
        items.append(
            {
                "snapshot_date": r.snapshot_date.isoformat(),
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "timeline_item_count": meta.get("timeline_item_count"),
                "feature_daily_present": meta.get("feature_daily_present"),
            }
        )
    return {"opportunity_id": opportunity_id, "items": items, "total": len(items)}


@router.get("/opportunities/{opportunity_id}/snapshots/{snapshot_date}", response_model=DealReplayFramesResponse)
async def get_replay_snapshot(
    opportunity_id: int,
    snapshot_date: date,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_deal_replay),
):
    await _ensure_opp_access(db, opportunity_id, current_user)
    row = (
        await db.execute(
            select(DealReplaySnapshot).where(
                DealReplaySnapshot.opportunity_id == opportunity_id,
                DealReplaySnapshot.snapshot_date == snapshot_date,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Snapshot bulunamadı")
    try:
        frames = json.loads(row.frames_json or "{}")
    except json.JSONDecodeError:
        frames = {}
    try:
        meta = json.loads(row.meta_json or "{}")
    except json.JSONDecodeError:
        meta = {}
    return {
        "opportunity_id": opportunity_id,
        "snapshot_date": row.snapshot_date.isoformat(),
        "source_timeline_version": row.source_timeline_version,
        "frames": frames,
        "meta": meta,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.post("/opportunities/{opportunity_id}/materialize", response_model=DealReplayMaterializeResponse)
async def post_materialize_replay_snapshot(
    opportunity_id: int,
    snapshot_date: date | None = Query(
        None,
        description="UTC takvim günü; boşsa bugün (UTC).",
    ),
    include_signals: bool = Query(True),
    include_legacy_opportunity_signals: bool = Query(True),
    timeline_limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_deal_replay),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS)),
):
    await _ensure_opp_access(db, opportunity_id, current_user)
    day = snapshot_date or datetime.now(timezone.utc).date()
    try:
        row = await materialize_deal_replay_snapshot(
            db,
            opportunity_id,
            day,
            timeline_limit=timeline_limit,
            include_signals=include_signals,
            include_legacy_opportunity_signals=include_legacy_opportunity_signals,
        )
        await db.commit()
    except ValueError as e:
        if str(e) == "opportunity_not_found":
            raise HTTPException(status_code=404, detail="Fırsat bulunamadı") from e
        raise

    try:
        meta = json.loads(row.meta_json or "{}")
    except json.JSONDecodeError:
        meta = {}
    return {
        "ok": True,
        "opportunity_id": opportunity_id,
        "snapshot_date": row.snapshot_date.isoformat(),
        "timeline_item_count": meta.get("timeline_item_count"),
    }
