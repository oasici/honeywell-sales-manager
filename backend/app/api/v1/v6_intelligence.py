"""V6 Intelligence Depth endpoints.

* ``GET  /v6/opportunities/{id}/replay-deltas`` — counterfactual deltas
* ``POST /v6/playbooks/promote-from-dna`` — manager-only DNA promoter
* ``GET  /v6/playbooks/{id}/adherence`` — refreshed adherence + lift snapshot

Gated by ``FEATURE_V5_INTELLIGENCE`` (V6 doesn't introduce a separate
flag — these endpoints are an algorithmic upgrade on top of V5).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services import (
    dna_playbook_promoter,
    replay_delta_service,
)
from app.services.tenant_context import assert_same_tenant


async def _load_opportunity(
    db: AsyncSession, opp_id: int, current_user: User
) -> Opportunity:
    """Load Opportunity by id with cross-tenant + missing checks.

    R4-TEN-21: previously this endpoint did a bare ``db.get(Opportunity)``
    which let a manager from tenant A enumerate replay-deltas on tenant
    B's deals. We now collapse "doesn't exist" and "exists in another
    tenant" into the same 404 response.
    """
    opp = await db.get(Opportunity, opp_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Fırsat bulunamadı")
    try:
        assert_same_tenant(opp, current_user, exception_cls=NotFoundException)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Fırsat bulunamadı")
    return opp


router = APIRouter(prefix="/v6", tags=["V6 Intelligence Depth"])


def _require_v5():
    if not settings.FEATURE_V5_INTELLIGENCE:
        raise HTTPException(status_code=404, detail="Not found")


def _opp_rbac_guard(current_user: User, opp: Opportunity) -> None:
    if (
        current_user.role == UserRole.SALES_REP.value
        and opp.owner_id is not None
        and int(opp.owner_id) != int(current_user.id)
    ):
        raise HTTPException(status_code=403, detail="Yetkisiz")


def _safe_loads(raw: str | None):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


# ─────────────────────── replay deltas ───────────────────────────────


@router.get("/opportunities/{opportunity_id}/replay-deltas")
async def list_replay_deltas(
    opportunity_id: int,
    refresh: bool = Query(False, description="Recompute deltas before listing"),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    opp = await _load_opportunity(db, opportunity_id, current_user)
    _opp_rbac_guard(current_user, opp)

    if refresh:
        await replay_delta_service.compute_deltas(db, opportunity_id=opportunity_id)
        await db.commit()

    rows = await replay_delta_service.list_deltas(
        db, opportunity_id=opportunity_id, limit=limit
    )
    return {
        "opportunity_id": opportunity_id,
        "items": [
            {
                "id": r.id,
                "from_ts": r.from_ts.isoformat() if r.from_ts else None,
                "to_ts": r.to_ts.isoformat() if r.to_ts else None,
                "change_type": r.change_type,
                "change_summary": r.change_summary,
                "impact_score": r.impact_score,
                "drivers": _safe_loads(r.drivers_json),
                "counterfactual_hint": r.counterfactual_hint,
            }
            for r in rows
        ],
        "total": len(rows),
    }


# ─────────────────────── DNA → Playbook promote ──────────────────────


@router.post("/playbooks/promote-from-dna")
async def promote_from_dna(
    min_lift: float = Query(1.5, ge=1.0, le=10.0),
    min_support: int = Query(10, ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    if current_user.role not in (
        UserRole.SALES_MANAGER.value,
        UserRole.OPERATIONS.value,
    ):
        raise HTTPException(status_code=403, detail="Yetkisiz")
    written = await dna_playbook_promoter.promote_top_patterns(
        db, min_lift=min_lift, min_support=min_support
    )
    await db.commit()
    return {"promoted": written}


@router.get("/playbooks/{playbook_id}/adherence")
async def get_playbook_adherence(
    playbook_id: int,
    window_days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    if current_user.role not in (
        UserRole.SALES_MANAGER.value,
        UserRole.OPERATIONS.value,
    ):
        raise HTTPException(status_code=403, detail="Yetkisiz")
    snap = await dna_playbook_promoter.compute_adherence(
        db, playbook_id=playbook_id, window_days=window_days
    )
    await db.commit()
    return {
        "playbook_id": playbook_id,
        "period_start": snap.period_start.isoformat() if snap.period_start else None,
        "period_end": snap.period_end.isoformat() if snap.period_end else None,
        "usage_count": snap.usage_count,
        "completion_rate": snap.completion_rate,
        "won_rate": snap.won_rate,
        "lift_vs_control": snap.lift_vs_control,
        "sample_size": snap.sample_size,
    }
