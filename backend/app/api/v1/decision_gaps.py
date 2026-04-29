from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.decision_gap import DecisionGap
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.user import User


router = APIRouter(prefix="/decision-gaps", tags=["Decision Gaps"])


def _require_v4():
    if not settings.FEATURE_V4_FEATURE_STORE:
        raise HTTPException(status_code=404, detail="Not found")


def _opp_rbac_guard(current_user: User, opp: Opportunity):
    if current_user.role == UserRole.SALES_REP.value and int(opp.owner_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Yetkisiz")


@router.get("/opportunities/{opportunity_id}")
async def list_opportunity_gaps(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v4),
):
    # V13 cross-tenant guard: load + 404 if missing or in sibling tenant.
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
    _opp_rbac_guard(current_user, opp)

    rows = (
        await db.execute(
            select(DecisionGap)
            .where(DecisionGap.opportunity_id == opportunity_id, DecisionGap.is_resolved.is_(False))
            .order_by(DecisionGap.severity.desc(), DecisionGap.created_at.desc())
        )
    ).scalars().all()

    def _loads(x: str | None):
        if not x:
            return None
        try:
            return json.loads(x)
        except Exception:
            return None

    return {
        "opportunity_id": opportunity_id,
        "items": [
            {
                "id": r.id,
                "gap_type": r.gap_type,
                "severity": r.severity,
                "expected_roles": _loads(r.expected_roles_json) or [],
                "observed_roles": _loads(r.observed_roles_json) or [],
                "recommended_actions": _loads(r.recommended_actions_json) or [],
                "drivers": _loads(r.drivers_json) or [],
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/cockpit/list")
async def cockpit_gaps(
    limit: int = Query(30, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v4),
):
    owner_filter = None
    if current_user.role == UserRole.SALES_REP.value:
        owner_filter = current_user.id

    conditions = [DecisionGap.is_resolved.is_(False), Opportunity.status == "active"]
    if owner_filter is not None:
        conditions.append(Opportunity.owner_id == owner_filter)

    rows = (
        await db.execute(
            select(
                DecisionGap.id,
                DecisionGap.opportunity_id,
                DecisionGap.gap_type,
                DecisionGap.severity,
                DecisionGap.recommended_actions_json,
                DecisionGap.created_at,
                Opportunity.title,
                Opportunity.stage,
                Opportunity.amount,
                Opportunity.currency,
            )
            .join(Opportunity, Opportunity.id == DecisionGap.opportunity_id)
            .where(and_(*conditions))
            .order_by(DecisionGap.severity.desc(), DecisionGap.created_at.desc())
            .limit(limit)
        )
    ).all()

    def first_action(x: str | None) -> str | None:
        if not x:
            return None
        try:
            arr = json.loads(x)
            if isinstance(arr, list) and arr:
                return str(arr[0])
        except Exception:
            return None
        return None

    return {
        "items": [
            {
                "id": int(r.id),
                "opportunity_id": int(r.opportunity_id),
                "title": r.title,
                "stage": r.stage,
                "amount": float(r.amount) if r.amount is not None else None,
                "currency": r.currency,
                "gap_type": r.gap_type,
                "severity": r.severity,
                "recommended_action": first_action(r.recommended_actions_json),
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }

