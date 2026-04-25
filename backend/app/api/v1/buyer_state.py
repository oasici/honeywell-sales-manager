from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.buyer_state_history import BuyerStateHistory
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.user import User


router = APIRouter(prefix="/buyer-state", tags=["Buyer State"])


def _require_v4():
    if not settings.FEATURE_V4_FEATURE_STORE:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/opportunities/{opportunity_id}/timeline")
async def get_buyer_state_timeline(
    opportunity_id: int,
    limit: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v4),
):
    # RBAC: reps can only access their own opportunities
    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Fırsat bulunamadı")
    if current_user.role == UserRole.SALES_REP.value and int(opp.owner_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Yetkisiz")

    rows = (
        await db.execute(
            select(BuyerStateHistory)
            .where(BuyerStateHistory.opportunity_id == opportunity_id)
            .order_by(BuyerStateHistory.snapshot_date.desc())
            .limit(limit)
        )
    ).scalars().all()

    return {
        "items": [
            {
                "snapshot_date": r.snapshot_date.isoformat(),
                "state": r.state,
                "confidence": r.confidence,
                "drivers": (json.loads(r.drivers_json).get("drivers", []) if r.drivers_json else []),
            }
            for r in rows
        ],
        "total": len(rows),
    }

