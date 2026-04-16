"""Leaderboard & gamification API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.leaderboard_service import LeaderboardService

router = APIRouter(prefix="/leaderboard", tags=["Leaderboard"])


@router.get("/")
async def get_leaderboard(
    period: str = Query("month", regex="^(week|month|quarter|year)$"),
    metric: str = Query("revenue", regex="^(revenue|deals_won|activities|response_time)$"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get ranked rep list by metric for period."""
    service = LeaderboardService(db)
    rankings = await service.get_leaderboard(period=period, metric=metric)
    return {"data": rankings}


@router.get("/achievements")
async def get_my_achievements(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's achievements, checking for new ones first."""
    service = LeaderboardService(db)
    new_achievements = await service.check_achievements(current_user.id)
    await db.commit()
    all_achievements = await service.get_user_achievements(current_user.id)
    return {
        "data": all_achievements,
        "new": new_achievements,
    }


@router.get("/achievements/{user_id}")
async def get_user_achievements(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get specific user's achievements (manager view)."""
    service = LeaderboardService(db)
    achievements = await service.get_user_achievements(user_id)
    return {"data": achievements}
