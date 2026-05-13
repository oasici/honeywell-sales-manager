"""Forecast adjustments and pipeline snapshots."""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import Date, and_, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.forecast import ForecastAdjustment, PipelineSnapshot
from app.models.opportunity import Opportunity
from app.services.tenant_context import assert_same_tenant

logger = logging.getLogger(__name__)

# Hardcoded fallback used when stage_configs table is empty
_FALLBACK_PROBABILITIES: dict[str, float] = {
    "prospecting": 0.1,
    "qualified": 0.3,
    "proposal": 0.5,
    "negotiation": 0.7,
    "closed_won": 1.0,
    "closed_lost": 0.0,
}

# Module-level cache cleared when stage configs are updated via settings API
_stage_probability_cache: dict[str, float] = {}


async def _get_stage_probabilities(db: AsyncSession) -> dict[str, float]:
    """Load stage probabilities from DB with fallback to defaults."""
    if _stage_probability_cache:
        return _stage_probability_cache

    from app.models.stage_config import StageConfig

    result = await db.execute(
        select(StageConfig).where(StageConfig.is_active.is_(True))
    )
    configs = result.scalars().all()

    if not configs:
        return _FALLBACK_PROBABILITIES

    probabilities = {
        c.stage_name: c.probability_pct / 100.0 for c in configs
    }
    _stage_probability_cache.update(probabilities)
    return probabilities


# Keep backward-compatible reference for any code that imports this directly
STAGE_PROBABILITIES: dict[str, float] = _FALLBACK_PROBABILITIES


class ForecastService:
    """Forecast adjustment CRUD and pipeline snapshot generation."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_adjustment(
        self,
        opp_id: int,
        user_id: int,
        new_amount: float | None = None,
        new_category: str | None = None,
        reason: str | None = None,
        current_user=None,
    ) -> ForecastAdjustment:
        """Save current values as original, apply new values to opportunity.

        Round-14 R14-AUTH-1 — when ``current_user`` is supplied, verify
        the opportunity belongs to the caller's tenant before mutating
        it. Pre-fix, a sales_manager from tenant A could post an
        adjustment to any tenant B opportunity simply by knowing the id.
        The parameter is keyword-only and defaults to ``None`` so legacy
        callers (cron jobs, in-tenant background workers) keep working;
        any user-facing router MUST pass it.
        """
        result = await self.db.execute(
            select(Opportunity).where(Opportunity.id == opp_id)
        )
        opportunity = result.scalar_one_or_none()
        if not opportunity:
            raise NotFoundException("Firsat bulunamadi")
        if current_user is not None:
            assert_same_tenant(
                opportunity, current_user, exception_cls=NotFoundException
            )

        original_amount = opportunity.amount or 0.0
        original_category = opportunity.forecast_category

        adjusted_amount = new_amount if new_amount is not None else original_amount
        adjusted_category = new_category if new_category is not None else original_category

        adjustment = ForecastAdjustment(
            opportunity_id=opp_id,
            adjusted_by=user_id,
            original_amount=original_amount,
            adjusted_amount=adjusted_amount,
            original_category=original_category,
            adjusted_category=adjusted_category,
            reason=reason,
        )
        self.db.add(adjustment)

        # Apply changes to the opportunity
        if new_amount is not None:
            opportunity.amount = new_amount
        if new_category is not None:
            opportunity.forecast_category = new_category

        await self.db.flush()
        await self.db.refresh(adjustment)
        return adjustment

    async def get_adjustments(
        self, opp_id: int, current_user=None
    ) -> list[ForecastAdjustment]:
        """Return adjustment history for an opportunity, newest first.

        Round-14 R14-AUTH-1 — when ``current_user`` is supplied, verify
        the parent opportunity belongs to the caller's tenant before
        returning the history (an adjustment carries no tenant_id of
        its own; the security boundary is the parent opportunity).
        """
        if current_user is not None:
            opportunity = (
                await self.db.execute(
                    select(Opportunity).where(Opportunity.id == opp_id)
                )
            ).scalar_one_or_none()
            if not opportunity:
                raise NotFoundException("Firsat bulunamadi")
            assert_same_tenant(
                opportunity, current_user, exception_cls=NotFoundException
            )

        result = await self.db.execute(
            select(ForecastAdjustment)
            .where(ForecastAdjustment.opportunity_id == opp_id)
            .order_by(ForecastAdjustment.created_at.desc())
        )
        return list(result.scalars().all())

    async def take_pipeline_snapshot(self) -> list[PipelineSnapshot]:
        """Create a snapshot of the current pipeline grouped by stage.

        Weighted amount = total_amount * stage probability.
        """
        today = date.today()

        result = await self.db.execute(
            select(
                Opportunity.stage,
                func.count(Opportunity.id).label("opp_count"),
                func.coalesce(func.sum(Opportunity.amount), 0.0).label("total"),
            )
            .where(Opportunity.status == "active")
            .group_by(Opportunity.stage)
        )
        rows = result.all()

        stage_probabilities = await _get_stage_probabilities(self.db)

        snapshots: list[PipelineSnapshot] = []
        for row in rows:
            stage = row[0]
            opp_count = row[1]
            total = float(row[2])
            probability = stage_probabilities.get(stage, 0.0)
            weighted = total * probability

            snapshot = PipelineSnapshot(
                snapshot_date=today,
                stage=stage,
                opportunity_count=opp_count,
                total_amount=total,
                weighted_amount=weighted,
            )
            self.db.add(snapshot)
            snapshots.append(snapshot)

        await self.db.flush()

        # Capture per-opportunity forecast detail for accuracy tracking
        from app.models.forecast_snapshot_detail import ForecastSnapshotDetail

        active_opps_q = await self.db.execute(
            select(
                Opportunity.id,
                Opportunity.forecast_category,
                Opportunity.amount,
                Opportunity.stage,
            ).where(Opportunity.status == "active")
        )

        # Map stages to snapshot IDs for linking
        snapshot_map = {s.stage: s.id for s in snapshots}

        for opp_row in active_opps_q.all():
            detail = ForecastSnapshotDetail(
                snapshot_id=snapshot_map.get(opp_row.stage),
                opportunity_id=opp_row.id,
                forecast_category=opp_row.forecast_category,
                amount=float(opp_row.amount or 0.0),
                stage=opp_row.stage,
            )
            self.db.add(detail)

        await self.db.flush()
        logger.info("Pipeline snapshot taken for %s: %d stages", today, len(snapshots))
        return snapshots

    async def get_snapshots(
        self, start_date: date | None = None, end_date: date | None = None,
    ) -> list[PipelineSnapshot]:
        """Get snapshots, optionally filtered by date range."""
        query = select(PipelineSnapshot).order_by(
            PipelineSnapshot.snapshot_date.desc(), PipelineSnapshot.stage,
        )

        conditions = []
        if start_date is not None:
            conditions.append(PipelineSnapshot.snapshot_date >= start_date)
        if end_date is not None:
            conditions.append(PipelineSnapshot.snapshot_date <= end_date)

        if conditions:
            query = query.where(and_(*conditions))

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_week_over_week(self, weeks: int = 4) -> list[dict]:
        """Compare pipeline snapshots from consecutive weeks.

        Returns a list of dicts, one per week, with stage breakdowns
        and deltas from the previous week.
        """
        today = date.today()
        weekly_data: list[dict] = []

        for i in range(weeks):
            week_end = today - timedelta(weeks=i)
            week_start = week_end - timedelta(days=6)

            result = await self.db.execute(
                select(PipelineSnapshot)
                .where(
                    and_(
                        PipelineSnapshot.snapshot_date >= week_start,
                        PipelineSnapshot.snapshot_date <= week_end,
                    )
                )
                .order_by(PipelineSnapshot.snapshot_date.desc())
            )
            snapshots = result.scalars().all()

            # Take the latest snapshot per stage within the week
            stage_map: dict[str, dict] = {}
            for snap in snapshots:
                if snap.stage not in stage_map:
                    stage_map[snap.stage] = {
                        "stage": snap.stage,
                        "opportunity_count": snap.opportunity_count,
                        "total_amount": snap.total_amount,
                        "weighted_amount": snap.weighted_amount,
                    }

            week_total = sum(s["total_amount"] for s in stage_map.values())
            week_weighted = sum(s["weighted_amount"] for s in stage_map.values())

            weekly_data.append({
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "stages": stage_map,
                "total_amount": week_total,
                "weighted_amount": week_weighted,
                "delta_amount": 0.0,
                "delta_weighted": 0.0,
            })

        # Calculate deltas (compare each week to the following week, i.e. older)
        for i in range(len(weekly_data) - 1):
            current = weekly_data[i]
            previous = weekly_data[i + 1]
            current["delta_amount"] = current["total_amount"] - previous["total_amount"]
            current["delta_weighted"] = current["weighted_amount"] - previous["weighted_amount"]

        return weekly_data

    async def get_team_forecast(self, manager_id: int | None = None) -> dict:
        """Rollup forecast by rep for a manager's team.

        Groups active opportunities by owner, sums amounts per forecast_category.
        If manager_id is provided, only include reps whose manager_id matches.
        If manager_id is None, returns all reps.
        """
        from app.models.user import User

        query = (
            select(
                Opportunity.owner_id,
                Opportunity.forecast_category,
                func.count(Opportunity.id).label("opp_count"),
                func.coalesce(func.sum(Opportunity.amount), 0.0).label("total_amount"),
            )
            .where(Opportunity.status == "active")
        )

        # Filter to reps managed by this manager
        if manager_id is not None:
            managed_ids = select(User.id).where(User.manager_id == manager_id)
            query = query.where(Opportunity.owner_id.in_(managed_ids))

        query = query.group_by(Opportunity.owner_id, Opportunity.forecast_category)
        result = await self.db.execute(query)
        rows = result.all()

        # Build per-rep rollup
        rep_map: dict[int, dict] = {}
        for row in rows:
            owner_id = row.owner_id
            if owner_id not in rep_map:
                rep_map[owner_id] = {
                    "owner_id": owner_id,
                    "categories": {},
                    "total_amount": 0.0,
                    "total_opps": 0,
                }
            cat = row.forecast_category or "pipeline"
            rep_map[owner_id]["categories"][cat] = {
                "count": row.opp_count,
                "amount": float(row.total_amount),
            }
            rep_map[owner_id]["total_amount"] += float(row.total_amount)
            rep_map[owner_id]["total_opps"] += row.opp_count

        # Enrich with user names
        if rep_map:
            users_result = await self.db.execute(
                select(User.id, User.full_name).where(User.id.in_(list(rep_map.keys())))
            )
            for u in users_result.all():
                if u.id in rep_map:
                    rep_map[u.id]["owner_name"] = u.full_name

        reps = list(rep_map.values())
        grand_total = sum(r["total_amount"] for r in reps)

        return {
            "reps": reps,
            "grand_total": grand_total,
            "rep_count": len(reps),
        }
