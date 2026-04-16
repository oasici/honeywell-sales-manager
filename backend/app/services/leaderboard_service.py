"""Leaderboard & gamification service — rankings and achievement tracking."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.achievement import Achievement
from app.models.activity_log import ActivityLog
from app.models.opportunity import Opportunity
from app.models.quote import Quote
from app.models.user import User

logger = logging.getLogger(__name__)

WEEK_DAYS = 7
MONTH_DAYS = 30
QUARTER_DAYS = 90
YEAR_DAYS = 365

PERIOD_DAYS_MAP: dict[str, int] = {
    "week": WEEK_DAYS,
    "month": MONTH_DAYS,
    "quarter": QUARTER_DAYS,
    "year": YEAR_DAYS,
}

FIRST_QUOTE_TYPE = "ilk_teklif"
TEN_DEALS_TYPE = "10_firsat"
STAR_OF_WEEK_TYPE = "haftanin_yildizi"
FAST_RESPONSE_TYPE = "hizli_cevap"
HUNDRED_ACTIVITIES_TYPE = "100_aktivite"
BIG_DEAL_TYPE = "buyuk_anlas"

BIG_DEAL_THRESHOLD = 100_000
FAST_RESPONSE_HOURS = 2
TEN_DEALS_COUNT = 10
HUNDRED_ACTIVITIES_COUNT = 100


class LeaderboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_leaderboard(
        self,
        period: str = "month",
        metric: str = "revenue",
    ) -> list[dict]:
        """Get ranked rep list by metric for period."""
        days = PERIOD_DAYS_MAP.get(period, MONTH_DAYS)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        prev_cutoff = cutoff - timedelta(days=days)

        current = await self._rank_by_metric(metric, cutoff)
        previous = await self._rank_by_metric(metric, prev_cutoff, cutoff)

        prev_map: dict[int, float] = {
            row["user_id"]: row["value"] for row in previous
        }

        result: list[dict] = []
        for rank, entry in enumerate(current, start=1):
            prev_value = prev_map.get(entry["user_id"], 0)
            delta = entry["value"] - prev_value
            result.append({
                "rank": rank,
                "user_id": entry["user_id"],
                "user_name": entry["user_name"],
                "value": entry["value"],
                "delta_vs_prev_period": round(delta, 2),
            })

        return result

    async def _rank_by_metric(
        self,
        metric: str,
        start: datetime,
        end: datetime | None = None,
    ) -> list[dict]:
        """Rank users by a specific metric within a time window."""
        end = end or datetime.now(timezone.utc)

        if metric == "revenue":
            return await self._rank_revenue(start, end)
        if metric == "deals_won":
            return await self._rank_deals_won(start, end)
        if metric == "activities":
            return await self._rank_activities(start, end)
        if metric == "response_time":
            return await self._rank_response_time(start, end)

        return await self._rank_revenue(start, end)

    async def _rank_revenue(
        self, start: datetime, end: datetime,
    ) -> list[dict]:
        """Rank by total won opportunity amount."""
        query = (
            select(
                Opportunity.owner_id.label("user_id"),
                User.full_name.label("user_name"),
                func.coalesce(func.sum(Opportunity.amount), 0).label("value"),
            )
            .join(User, User.id == Opportunity.owner_id)
            .where(
                and_(
                    Opportunity.status == "closed",
                    Opportunity.stage == "closed_won",
                    Opportunity.updated_at >= start,
                    Opportunity.updated_at < end,
                ),
            )
            .group_by(Opportunity.owner_id, User.full_name)
            .order_by(func.sum(Opportunity.amount).desc())
        )
        rows = (await self.db.execute(query)).all()
        return [
            {"user_id": r.user_id, "user_name": r.user_name, "value": round(float(r.value), 2)}
            for r in rows
        ]

    async def _rank_deals_won(
        self, start: datetime, end: datetime,
    ) -> list[dict]:
        """Rank by count of won opportunities."""
        query = (
            select(
                Opportunity.owner_id.label("user_id"),
                User.full_name.label("user_name"),
                func.count(Opportunity.id).label("value"),
            )
            .join(User, User.id == Opportunity.owner_id)
            .where(
                and_(
                    Opportunity.status == "closed",
                    Opportunity.stage == "closed_won",
                    Opportunity.updated_at >= start,
                    Opportunity.updated_at < end,
                ),
            )
            .group_by(Opportunity.owner_id, User.full_name)
            .order_by(func.count(Opportunity.id).desc())
        )
        rows = (await self.db.execute(query)).all()
        return [
            {"user_id": r.user_id, "user_name": r.user_name, "value": int(r.value)}
            for r in rows
        ]

    async def _rank_activities(
        self, start: datetime, end: datetime,
    ) -> list[dict]:
        """Rank by total activity count."""
        query = (
            select(
                ActivityLog.user_id.label("user_id"),
                User.full_name.label("user_name"),
                func.count(ActivityLog.id).label("value"),
            )
            .join(User, User.id == ActivityLog.user_id)
            .where(
                and_(
                    ActivityLog.user_id.isnot(None),
                    ActivityLog.created_at >= start,
                    ActivityLog.created_at < end,
                ),
            )
            .group_by(ActivityLog.user_id, User.full_name)
            .order_by(func.count(ActivityLog.id).desc())
        )
        rows = (await self.db.execute(query)).all()
        return [
            {"user_id": r.user_id, "user_name": r.user_name, "value": int(r.value)}
            for r in rows
        ]

    async def _rank_response_time(
        self, start: datetime, end: datetime,
    ) -> list[dict]:
        """Rank by average response time (lower is better)."""
        query = (
            select(
                ActivityLog.user_id.label("user_id"),
                User.full_name.label("user_name"),
                func.avg(ActivityLog.duration_minutes).label("value"),
            )
            .join(User, User.id == ActivityLog.user_id)
            .where(
                and_(
                    ActivityLog.user_id.isnot(None),
                    ActivityLog.duration_minutes.isnot(None),
                    ActivityLog.created_at >= start,
                    ActivityLog.created_at < end,
                ),
            )
            .group_by(ActivityLog.user_id, User.full_name)
            .order_by(func.avg(ActivityLog.duration_minutes).asc())
        )
        rows = (await self.db.execute(query)).all()
        return [
            {
                "user_id": r.user_id,
                "user_name": r.user_name,
                "value": round(float(r.value) / 60, 1) if r.value else 0,
            }
            for r in rows
        ]

    async def check_achievements(self, user_id: int) -> list[dict]:
        """Check and award new achievements for a user."""
        existing_q = await self.db.execute(
            select(Achievement.achievement_type).where(
                Achievement.user_id == user_id,
            )
        )
        existing_types = {r[0] for r in existing_q.all()}

        newly_earned: list[dict] = []

        checks = [
            self._check_first_quote,
            self._check_ten_deals,
            self._check_star_of_week,
            self._check_fast_response,
            self._check_hundred_activities,
            self._check_big_deal,
        ]
        for check_fn in checks:
            result = await check_fn(user_id, existing_types)
            if result:
                newly_earned.append(result)

        return newly_earned

    async def _award(
        self,
        user_id: int,
        achievement_type: str,
        title: str,
        description: str,
        metadata: dict | None = None,
    ) -> dict:
        """Create an achievement record and return it."""
        # Convert Decimal values to float for JSON serialization
        safe_metadata = None
        if metadata:
            safe_metadata = {k: float(v) if hasattr(v, 'as_integer_ratio') else v for k, v in metadata.items()}
        achievement = Achievement(
            user_id=user_id,
            achievement_type=achievement_type,
            title=title,
            description=description,
            metadata_json=json.dumps(safe_metadata) if safe_metadata else None,
        )
        self.db.add(achievement)
        await self.db.flush()
        return {
            "id": achievement.id,
            "achievement_type": achievement_type,
            "title": title,
            "description": description,
            "earned_at": achievement.earned_at.isoformat(),
        }

    async def _check_first_quote(
        self, user_id: int, existing: set[str],
    ) -> dict | None:
        if FIRST_QUOTE_TYPE in existing:
            return None
        count = (await self.db.execute(
            select(func.count(Quote.id)).where(Quote.created_by == user_id)
        )).scalar() or 0
        if count > 0:
            return await self._award(
                user_id, FIRST_QUOTE_TYPE,
                "Ilk Teklif", "Ilk teklifinizi olusturdunuz",
            )
        return None

    async def _check_ten_deals(
        self, user_id: int, existing: set[str],
    ) -> dict | None:
        if TEN_DEALS_TYPE in existing:
            return None
        count = (await self.db.execute(
            select(func.count(Opportunity.id)).where(
                and_(
                    Opportunity.owner_id == user_id,
                    Opportunity.stage == "closed_won",
                ),
            )
        )).scalar() or 0
        if count >= TEN_DEALS_COUNT:
            return await self._award(
                user_id, TEN_DEALS_TYPE,
                "10 Firsat Kazanildi", "10 firsati basariyla kapattiniz",
                {"count": count},
            )
        return None

    async def _check_star_of_week(
        self, user_id: int, existing: set[str],
    ) -> dict | None:
        week_ago = datetime.now(timezone.utc) - timedelta(days=WEEK_DAYS)
        top_q = await self.db.execute(
            select(Opportunity.owner_id)
            .where(
                and_(
                    Opportunity.stage == "closed_won",
                    Opportunity.updated_at >= week_ago,
                ),
            )
            .group_by(Opportunity.owner_id)
            .order_by(func.sum(Opportunity.amount).desc())
            .limit(1)
        )
        top_user = top_q.scalar()
        if top_user == user_id and STAR_OF_WEEK_TYPE not in existing:
            return await self._award(
                user_id, STAR_OF_WEEK_TYPE,
                "Haftanin Yildizi", "Bu hafta en yuksek geliri siz kazandiniz",
            )
        return None

    async def _check_fast_response(
        self, user_id: int, existing: set[str],
    ) -> dict | None:
        if FAST_RESPONSE_TYPE in existing:
            return None
        avg_minutes = (await self.db.execute(
            select(func.avg(ActivityLog.duration_minutes)).where(
                and_(
                    ActivityLog.user_id == user_id,
                    ActivityLog.duration_minutes.isnot(None),
                ),
            )
        )).scalar()
        if avg_minutes is not None and avg_minutes < FAST_RESPONSE_HOURS * 60:
            return await self._award(
                user_id, FAST_RESPONSE_TYPE,
                "Hizli Cevap", "Ortalama cevap sureniz 2 saatin altinda",
                {"avg_hours": round(avg_minutes / 60, 1)},
            )
        return None

    async def _check_hundred_activities(
        self, user_id: int, existing: set[str],
    ) -> dict | None:
        if HUNDRED_ACTIVITIES_TYPE in existing:
            return None
        count = (await self.db.execute(
            select(func.count(ActivityLog.id)).where(
                ActivityLog.user_id == user_id,
            )
        )).scalar() or 0
        if count >= HUNDRED_ACTIVITIES_COUNT:
            return await self._award(
                user_id, HUNDRED_ACTIVITIES_TYPE,
                "100 Aktivite", "Toplam 100 aktiviteye ulastiniz",
                {"count": count},
            )
        return None

    async def _check_big_deal(
        self, user_id: int, existing: set[str],
    ) -> dict | None:
        if BIG_DEAL_TYPE in existing:
            return None
        max_amount = (await self.db.execute(
            select(func.max(Opportunity.amount)).where(
                and_(
                    Opportunity.owner_id == user_id,
                    Opportunity.stage == "closed_won",
                ),
            )
        )).scalar()
        if max_amount is not None and max_amount > BIG_DEAL_THRESHOLD:
            return await self._award(
                user_id, BIG_DEAL_TYPE,
                "Buyuk Anlasma", "100.000 uzerinde bir anlasma kapattiniz",
                {"amount": max_amount},
            )
        return None

    async def get_user_achievements(self, user_id: int) -> list[dict]:
        """Get all achievements for a user."""
        query = (
            select(Achievement)
            .where(Achievement.user_id == user_id)
            .order_by(Achievement.earned_at.desc())
        )
        rows = (await self.db.execute(query)).scalars().all()
        return [
            {
                "id": a.id,
                "achievement_type": a.achievement_type,
                "title": a.title,
                "description": a.description,
                "earned_at": a.earned_at.isoformat() if a.earned_at else None,
                "metadata": json.loads(a.metadata_json) if a.metadata_json else None,
            }
            for a in rows
        ]
