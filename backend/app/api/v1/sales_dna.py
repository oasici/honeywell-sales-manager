from __future__ import annotations

import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.sales_dna_snapshot import SalesDnaSnapshot
from app.models.user import User
from app.services.sales_dna_service import materialize_sales_dna_snapshot
from app.schemas.common import ItemsResponse

router = APIRouter(prefix="/v4/dna", tags=["V4 Sales DNA"])


def _require_sales_dna():
    if not settings.FEATURE_V4_SALES_DNA:
        raise HTTPException(status_code=404, detail="Not found")


async def _ensure_opp_access(
    db: AsyncSession, opportunity_id: int, current_user: User
) -> Opportunity:
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
async def list_dna_snapshots(
    opportunity_id: int,
    limit: int = Query(60, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_sales_dna),
):
    await _ensure_opp_access(db, opportunity_id, current_user)
    rows = (
        await db.execute(
            select(SalesDnaSnapshot)
            .where(SalesDnaSnapshot.opportunity_id == opportunity_id)
            .order_by(SalesDnaSnapshot.snapshot_date.desc())
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
                "miner_version": r.miner_version,
                "feature_daily_present": meta.get("feature_daily_present"),
            }
        )
    return {"opportunity_id": opportunity_id, "items": items, "total": len(items)}


@router.get("/opportunities/{opportunity_id}/latest", response_model=dict)
async def get_latest_dna(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_sales_dna),
):
    await _ensure_opp_access(db, opportunity_id, current_user)
    row = (
        await db.execute(
            select(SalesDnaSnapshot)
            .where(SalesDnaSnapshot.opportunity_id == opportunity_id)
            .order_by(SalesDnaSnapshot.snapshot_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="DNA snapshot yok — önce materialize edin")
    try:
        traits = json.loads(row.traits_json or "{}")
    except json.JSONDecodeError:
        traits = {}
    try:
        meta = json.loads(row.meta_json or "{}")
    except json.JSONDecodeError:
        meta = {}
    return {
        "opportunity_id": opportunity_id,
        "snapshot_date": row.snapshot_date.isoformat(),
        "traits": traits,
        "meta": meta,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/opportunities/{opportunity_id}/snapshots/{snapshot_date}", response_model=dict)
async def get_dna_snapshot(
    opportunity_id: int,
    snapshot_date: date,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_sales_dna),
):
    await _ensure_opp_access(db, opportunity_id, current_user)
    row = (
        await db.execute(
            select(SalesDnaSnapshot).where(
                SalesDnaSnapshot.opportunity_id == opportunity_id,
                SalesDnaSnapshot.snapshot_date == snapshot_date,
            )
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Snapshot bulunamadı")
    try:
        traits = json.loads(row.traits_json or "{}")
    except json.JSONDecodeError:
        traits = {}
    try:
        meta = json.loads(row.meta_json or "{}")
    except json.JSONDecodeError:
        meta = {}
    return {
        "opportunity_id": opportunity_id,
        "snapshot_date": row.snapshot_date.isoformat(),
        "traits": traits,
        "meta": meta,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.post("/opportunities/{opportunity_id}/materialize", response_model=dict)
async def post_materialize_dna(
    opportunity_id: int,
    snapshot_date: date | None = Query(None, description="UTC takvim günü; boşsa bugün (UTC)."),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_sales_dna),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS)),
):
    await _ensure_opp_access(db, opportunity_id, current_user)
    day = snapshot_date or datetime.now(timezone.utc).date()
    try:
        row = await materialize_sales_dna_snapshot(db, opportunity_id, day)
        await db.commit()
    except ValueError as e:
        if str(e) == "opportunity_not_found":
            raise HTTPException(status_code=404, detail="Fırsat bulunamadı") from e
        raise

    try:
        traits = json.loads(row.traits_json or "{}")
    except json.JSONDecodeError:
        traits = {}
    return {
        "ok": True,
        "opportunity_id": opportunity_id,
        "snapshot_date": row.snapshot_date.isoformat(),
        "risk_posture": traits.get("risk_posture"),
        "coaching_hooks": traits.get("coaching_hooks"),
    }
