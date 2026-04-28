"""V10 — spare parts intelligence endpoints (read-only layer).

Routes mounted under ``/api/v1/v10/parts-intel/``. All routes are
gated by ``FEATURE_V10_PARTS_INTEL``; when the flag is off the router
returns 404 indistinguishably so callers can't probe whether the
deployment runs the intel layer.

The endpoints map 1:1 to the service primitives:

- ``/velocity`` — Pareto A/B/C tier list
- ``/heatmap`` — month × part demand frequency
- ``/dead-stock`` — frozen-capital ledger
- ``/summary`` — combined dashboard payload (counts + totals)
- ``/inflation-tax`` — drift × open-pipeline exposure
- ``/stale-pricing`` — parts with expired/old price entries
- ``/margin-health`` — derived margin slippage alerts
- ``/obsolescence-watch`` — top-N EOL risk parts
- ``/parts/{id}/eol-risk`` — per-part risk envelope
- ``/last-time-buy`` — buy-now candidates
- ``/data-health`` — master-data completeness score
- ``/duplicates`` — likely-duplicate SparePart pairs
- ``/orphan-pricing`` — PriceEntry → inactive/missing SparePart
- ``/parts/{id}/substitutions`` — V9 revision-tree swap patterns
- ``/parts/{id}/cross-customer`` — distinct customers using the part
- ``/parts/{id}/segment-affinity`` — industries that quote the part most
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.enums import UserRole
from app.models.user import User
from app.services import (
    parts_data_quality_service,
    parts_intelligence_service,
    parts_obsolescence_watch_service,
    parts_pricing_intel_service,
    parts_substitution_service,
)


router = APIRouter(prefix="/v10/parts-intel", tags=["V10 Spare Parts Intelligence"])


def _require_v10():
    """Reject when V10 is off — looks like the route doesn't exist."""
    if not getattr(settings, "FEATURE_V10_PARTS_INTEL", False):
        raise HTTPException(status_code=404, detail="Not found")


def _tenant(user: User) -> int | None:
    """Extract tenant scope; None for single-tenant deployments."""
    return getattr(user, "tenant_id", None)


def _manager_or_admin_only(user: User) -> None:
    """Pareto / dead-stock / obsolescence views are manager-tier."""
    if user.role not in (
        UserRole.SALES_MANAGER.value,
        UserRole.ADMIN.value,
        UserRole.OPERATIONS.value,
    ):
        raise HTTPException(status_code=403, detail="Yetkisiz")


# ─────────────────────── Sprint AA — foundation ───────────────────────


@router.get("/summary")
async def get_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    _manager_or_admin_only(current_user)
    return await parts_intelligence_service.parts_intelligence_summary(
        db, tenant_id=_tenant(current_user)
    )


@router.get("/velocity")
async def get_velocity(
    tier: str | None = Query(None, pattern="^[ABC]$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    _manager_or_admin_only(current_user)
    rows = await parts_intelligence_service.velocity_classification(
        db, tenant_id=_tenant(current_user)
    )
    if tier:
        rows = [r for r in rows if r.tier == tier]
    return {"items": [asdict(r) for r in rows], "total": len(rows)}


@router.get("/heatmap")
async def get_heatmap(
    window_days: int = Query(180, ge=30, le=720),
    part_id: int | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    cells = await parts_intelligence_service.demand_heatmap(
        db,
        window_days=window_days,
        part_id=part_id,
        tenant_id=_tenant(current_user),
    )
    return {"items": [asdict(c) for c in cells], "total": len(cells)}


@router.get("/dead-stock")
async def get_dead_stock(
    min_idle_days: int = Query(180, ge=30, le=720),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    _manager_or_admin_only(current_user)
    rows = await parts_intelligence_service.dead_stock_ledger(
        db,
        min_idle_days=min_idle_days,
        tenant_id=_tenant(current_user),
        limit=limit,
    )
    frozen_total = sum(r.frozen_capital_estimate for r in rows)
    return {
        "items": [
            {
                "spare_part_id": r.spare_part_id,
                "honeywell_code": r.honeywell_code,
                "name": r.name,
                "supplier_price": r.supplier_price,
                "frozen_capital_estimate": r.frozen_capital_estimate,
                "last_quoted_at": r.last_quoted_at.isoformat() if r.last_quoted_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
        "frozen_capital_total": round(frozen_total, 2),
    }


# ─────────────────────── Sprint BB — pricing intel ─────────────────────


@router.get("/inflation-tax")
async def get_inflation_tax(
    months: int = Query(12, ge=3, le=36),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    _manager_or_admin_only(current_user)
    return await parts_pricing_intel_service.inflation_tax_summary(
        db, tenant_id=_tenant(current_user), months=months
    )


@router.get("/stale-pricing")
async def get_stale_pricing(
    max_age_days: int = Query(180, ge=30, le=720),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    rows = await parts_pricing_intel_service.stale_pricing_alerts(
        db,
        max_age_days=max_age_days,
        tenant_id=_tenant(current_user),
        limit=limit,
    )
    return {
        "items": [
            {
                "spare_part_id": r.spare_part_id,
                "honeywell_code": r.honeywell_code,
                "name": r.name,
                "last_price_at": r.last_price_at.isoformat() if r.last_price_at else None,
                "valid_until": r.valid_until.isoformat() if r.valid_until else None,
                "age_days": r.age_days,
                "reason": r.reason,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/margin-health")
async def get_margin_health(
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    rows = await parts_pricing_intel_service.margin_health_alerts(
        db, tenant_id=_tenant(current_user), limit=limit
    )
    return {"items": [asdict(r) for r in rows], "total": len(rows)}


# ─────────────────────── Sprint CC — obsolescence watch ───────────────


@router.get("/obsolescence-watch")
async def get_obsolescence_watch(
    top_n: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    _manager_or_admin_only(current_user)
    rows = await parts_obsolescence_watch_service.obsolescence_watch_list(
        db, tenant_id=_tenant(current_user), top_n=top_n
    )
    return {"items": [asdict(r) for r in rows], "total": len(rows)}


@router.get("/parts/{part_id}/eol-risk")
async def get_eol_risk(
    part_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    return await parts_obsolescence_watch_service.eol_risk_score(
        db, part_id=part_id, tenant_id=_tenant(current_user)
    )


@router.get("/last-time-buy")
async def get_last_time_buy(
    decay_threshold: float = Query(0.5, ge=0.0, le=1.0),
    pipeline_value_threshold: float = Query(5_000.0, ge=0.0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    _manager_or_admin_only(current_user)
    rows = await parts_obsolescence_watch_service.last_time_buy_recommendations(
        db,
        tenant_id=_tenant(current_user),
        decay_threshold=decay_threshold,
        pipeline_value_threshold=pipeline_value_threshold,
    )
    return {"items": rows, "total": len(rows)}


# ─────────────────────── Sprint DD — data quality ──────────────────────


@router.get("/data-health")
async def get_data_health(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    _manager_or_admin_only(current_user)
    return await parts_data_quality_service.master_data_health_score(
        db, tenant_id=_tenant(current_user)
    )


@router.get("/duplicates")
async def get_duplicates(
    threshold: float = Query(0.85, ge=0.0, le=1.0),
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    _manager_or_admin_only(current_user)
    rows = await parts_data_quality_service.duplicate_candidates(
        db,
        tenant_id=_tenant(current_user),
        threshold=threshold,
        limit=limit,
    )
    return {"items": [asdict(r) for r in rows], "total": len(rows)}


@router.get("/orphan-pricing")
async def get_orphan_pricing(
    limit: int = Query(200, ge=1, le=1000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    _manager_or_admin_only(current_user)
    rows = await parts_data_quality_service.orphan_pricing(db, limit=limit)
    return {
        "items": [
            {
                "price_entry_id": r.price_entry_id,
                "spare_part_id": r.spare_part_id,
                "list_price": r.list_price,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "reason": r.reason,
            }
            for r in rows
        ],
        "total": len(rows),
    }


# ─────────────────────── Sprint EE — substitution + segment ───────────


@router.get("/parts/{part_id}/substitutions")
async def get_substitutions(
    part_id: int,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    rows = await parts_substitution_service.substitution_patterns(
        db, part_id=part_id, tenant_id=_tenant(current_user), limit=limit
    )
    return {"items": [asdict(r) for r in rows], "total": len(rows)}


@router.get("/parts/{part_id}/cross-customer")
async def get_cross_customer(
    part_id: int,
    months: int = Query(12, ge=1, le=36),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    rows = await parts_substitution_service.cross_customer_demand(
        db,
        part_id=part_id,
        tenant_id=_tenant(current_user),
        months=months,
        limit=limit,
    )
    return {
        "items": [
            {
                "customer_id": r.customer_id,
                "customer_name": r.customer_name,
                "company": r.company,
                "industry": r.industry,
                "quote_count": r.quote_count,
                "last_quoted_at": r.last_quoted_at.isoformat()
                if r.last_quoted_at
                else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/parts/{part_id}/segment-affinity")
async def get_segment_affinity(
    part_id: int,
    months: int = Query(12, ge=1, le=36),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v10),
):
    rows = await parts_substitution_service.segment_affinity(
        db, part_id=part_id, tenant_id=_tenant(current_user), months=months
    )
    return {"items": [asdict(r) for r in rows], "total": len(rows)}
