"""Coaching Engine API — rep performance scoring, plans, and recommendations."""

from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.coaching_plan import CoachingPlan
from app.models.coaching_snapshot import CoachingSnapshot
from app.models.enums import UserRole
from app.models.user import User
from app.services.coaching_service import CoachingService

router = APIRouter(prefix="/coaching", tags=["Coaching Engine"])


def _require_cockpit():
    if not settings.FEATURE_REVENUE_COCKPIT:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/overview")
async def coaching_overview(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Manager-only: coaching overview for all reps."""
    service = CoachingService(db)
    results = await service.evaluate_all_reps()

    summary = {
        "total_reps": len(results),
        "healthy": sum(1 for r in results if r.get("risk_level") == "healthy"),
        "needs_improvement": sum(
            1 for r in results if r.get("risk_level") == "needs_improvement"
        ),
        "at_risk": sum(1 for r in results if r.get("risk_level") == "at_risk"),
        "avg_score": (
            round(sum(r.get("score", 0) for r in results) / len(results))
            if results
            else 0
        ),
    }

    return {"summary": summary, "reps": results}


# ── Pydantic Schemas ──


class CoachingPlanCreate(BaseModel):
    user_id: int
    goals_json: str = Field(..., min_length=2)
    weeks: int = Field(default=4, ge=1, le=52)
    start_date: date | None = None


# ── Plan Endpoints ──


@router.get("/plans")
async def list_coaching_plans(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Manager-only: list all coaching plans."""
    result = await db.execute(
        select(CoachingPlan).order_by(CoachingPlan.created_at.desc())
    )
    plans = result.scalars().all()

    return {
        "items": [
            {
                "id": p.id,
                "user_id": p.user_id,
                "user_name": p.user.full_name if p.user else None,
                "manager_id": p.manager_id,
                "goals_json": p.goals_json,
                "weeks": p.weeks,
                "start_date": p.start_date.isoformat() if p.start_date else None,
                "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in plans
        ],
        "total": len(plans),
    }


@router.post("/plans", status_code=201)
async def create_coaching_plan(
    body: CoachingPlanCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Manager-only: create a coaching plan for a rep."""
    # Validate goals_json is valid JSON
    try:
        json.loads(body.goals_json)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=400, detail="goals_json gecerli JSON formati olmali")

    # Verify target user exists
    user_result = await db.execute(select(User).where(User.id == body.user_id))
    target_user = user_result.scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="Hedef kullanici bulunamadi")

    plan = CoachingPlan(
        user_id=body.user_id,
        manager_id=current_user.id,
        goals_json=body.goals_json,
        weeks=body.weeks,
        start_date=body.start_date or date.today(),
        status="active",
    )
    db.add(plan)
    await db.flush()

    return {
        "message": "Kocluk plani olusturuldu",
        "id": plan.id,
        "user_id": plan.user_id,
    }


# ── Trend & Benchmark Endpoints ──


@router.get("/rep/{user_id}/trends")
async def coaching_rep_trends(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Score history from coaching snapshots. Manager sees all, rep sees self."""
    is_manager = current_user.role == UserRole.SALES_MANAGER.value
    is_self = current_user.id == user_id

    if not is_manager and not is_self:
        raise HTTPException(
            status_code=403,
            detail="Bu temsilcinin trend verisine erisim yetkiniz yok.",
        )

    result = await db.execute(
        select(CoachingSnapshot)
        .where(CoachingSnapshot.user_id == user_id)
        .order_by(CoachingSnapshot.created_at.desc())
        .limit(30)
    )
    snapshots = result.scalars().all()

    return {
        "user_id": user_id,
        "snapshots": [
            {
                "id": s.id,
                "score": s.score,
                "indicators_json": s.indicators_json,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in snapshots
        ],
        "total": len(snapshots),
    }


@router.get("/benchmarks")
async def coaching_benchmarks(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Percentile rankings across the team based on latest snapshots."""
    # Get the latest snapshot per user via subquery
    latest_subq = (
        select(
            CoachingSnapshot.user_id,
            func.max(CoachingSnapshot.created_at).label("max_created"),
        )
        .group_by(CoachingSnapshot.user_id)
        .subquery()
    )

    result = await db.execute(
        select(CoachingSnapshot)
        .join(
            latest_subq,
            (CoachingSnapshot.user_id == latest_subq.c.user_id)
            & (CoachingSnapshot.created_at == latest_subq.c.max_created),
        )
        .order_by(CoachingSnapshot.score.desc())
    )
    snapshots = result.scalars().all()

    if not snapshots:
        return {"benchmarks": [], "total": 0}

    total = len(snapshots)
    benchmarks = []
    for rank, snap in enumerate(snapshots, start=1):
        percentile = round((total - rank) / total * 100) if total > 1 else 100
        benchmarks.append({
            "user_id": snap.user_id,
            "user_name": snap.user.full_name if snap.user else None,
            "score": snap.score,
            "rank": rank,
            "percentile": percentile,
            "snapshot_date": snap.created_at.isoformat() if snap.created_at else None,
        })

    return {"benchmarks": benchmarks, "total": total}


@router.get("/rep/{user_id}")
async def coaching_rep(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_cockpit),
):
    """Rep coaching detail. Manager can view anyone; rep can view self only."""
    is_manager = current_user.role == UserRole.SALES_MANAGER.value
    is_self = current_user.id == user_id

    if not is_manager and not is_self:
        raise HTTPException(
            status_code=403,
            detail="Bu temsilcinin koçluk verisine erisim yetkiniz yok.",
        )

    service = CoachingService(db)
    result = await service.evaluate_rep(user_id)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result
