"""Revenue Leak Detection Service — scan active opportunities for leak indicators."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.opportunity import Opportunity, OpportunitySignal

logger = logging.getLogger(__name__)

STAGE_ORDER = {
    "prospecting": 1,
    "qualified": 2,
    "proposal": 3,
    "negotiation": 4,
    "closed_won": 5,
}

BACKWARD_STAGE_SCORE = 30
CLOSE_DATE_PUSH_SCORE = 25
AMOUNT_DECREASE_SCORE = 25
NO_ACTIVITY_SCORE = 20
NEGATIVE_SIGNAL_SCORE = 15
NO_ACTIVITY_THRESHOLD_DAYS = 14
MAX_LEAK_SCORE = 100
MAX_RESULTS = 20
PERCENTAGE_MULTIPLIER = 100


class LeakDetectionService:
    """Detect revenue leak indicators across active opportunities."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def detect_leaks(self) -> dict:
        """Scan all active opportunities for revenue leak indicators.

        Leak factors:
        - backward_stage: moved to earlier stage (e.g. negotiation -> proposal)
        - close_date_push: close_date moved to later date
        - amount_decrease: deal amount decreased
        - no_activity: no activity in 14+ days
        - negative_signals: has unresolved negative signals
        """
        opps = (await self.db.execute(
            select(Opportunity).where(Opportunity.status == "active")
        )).scalars().all()

        now = datetime.now(timezone.utc)
        activity_cutoff = now - timedelta(days=NO_ACTIVITY_THRESHOLD_DAYS)

        leaks: list[dict] = []
        total_leak_amount = 0.0

        for opp in opps:
            factors: list[dict] = []
            leak_score = 0

            # Check backward stage movement
            leak_score = self._check_backward_stage(opp, factors, leak_score)

            # Check close_date push
            leak_score = self._check_close_date_push(opp, factors, leak_score)

            # Check amount decrease
            leak_score = self._check_amount_decrease(opp, factors, leak_score)

            # Check no activity (14+ days)
            leak_score = await self._check_no_activity(
                opp, factors, leak_score, activity_cutoff, now,
            )

            # Check negative signals
            leak_score = await self._check_negative_signals(opp, factors, leak_score)

            if leak_score > 0:
                leaks.append({
                    "opportunity_id": opp.id,
                    "title": opp.title,
                    "stage": opp.stage,
                    "amount": opp.amount or 0,
                    "leak_score": min(leak_score, MAX_LEAK_SCORE),
                    "factors": factors,
                    "owner_name": opp.owner.full_name if opp.owner else "",
                })
                total_leak_amount += opp.amount or 0

        # Sort by leak_score descending
        leaks.sort(key=lambda x: x["leak_score"], reverse=True)

        return {
            "total_leaks": len(leaks),
            "total_leak_amount": total_leak_amount,
            "items": leaks[:MAX_RESULTS],
        }

    @staticmethod
    def _check_backward_stage(
        opp: Opportunity,
        factors: list[dict],
        leak_score: int,
    ) -> int:
        if opp.previous_stage:
            prev_order = STAGE_ORDER.get(opp.previous_stage, 0)
            curr_order = STAGE_ORDER.get(opp.stage, 0)
            if curr_order < prev_order:
                factors.append({
                    "name": "backward_stage",
                    "label": "Geri Adim",
                    "detail": f"{opp.previous_stage} -> {opp.stage}",
                })
                leak_score += BACKWARD_STAGE_SCORE
        return leak_score

    @staticmethod
    def _check_close_date_push(
        opp: Opportunity,
        factors: list[dict],
        leak_score: int,
    ) -> int:
        if opp.previous_close_date and opp.close_date:
            if opp.close_date > opp.previous_close_date:
                days_pushed = (opp.close_date - opp.previous_close_date).days
                factors.append({
                    "name": "close_date_push",
                    "label": "Tarih Erteleme",
                    "detail": f"{days_pushed} gun ileri",
                })
                leak_score += CLOSE_DATE_PUSH_SCORE
        return leak_score

    @staticmethod
    def _check_amount_decrease(
        opp: Opportunity,
        factors: list[dict],
        leak_score: int,
    ) -> int:
        if opp.previous_amount and opp.amount:
            if opp.amount < opp.previous_amount:
                decrease_pct = (
                    (opp.previous_amount - opp.amount) / opp.previous_amount
                ) * PERCENTAGE_MULTIPLIER
                factors.append({
                    "name": "amount_decrease",
                    "label": "Tutar Dususu",
                    "detail": f"%{decrease_pct:.0f} azalma",
                })
                leak_score += AMOUNT_DECREASE_SCORE
        return leak_score

    async def _check_no_activity(
        self,
        opp: Opportunity,
        factors: list[dict],
        leak_score: int,
        activity_cutoff: datetime,
        now: datetime,
    ) -> int:
        last_activity = (await self.db.execute(
            select(func.max(ActivityLog.created_at))
            .where(ActivityLog.opportunity_id == opp.id)
        )).scalar()

        if last_activity is None:
            factors.append({
                "name": "no_activity",
                "label": "Aktivite Yok",
                "detail": "Hic aktivite kaydedilmemis",
            })
            leak_score += NO_ACTIVITY_SCORE
        elif last_activity < activity_cutoff:
            if last_activity.tzinfo is None:
                last_activity = last_activity.replace(tzinfo=timezone.utc)
            days_inactive = (now - last_activity).days
            factors.append({
                "name": "no_activity",
                "label": "Aktivite Yok",
                "detail": f"{days_inactive} gundur aktivite yok",
            })
            leak_score += NO_ACTIVITY_SCORE

        return leak_score

    async def _check_negative_signals(
        self,
        opp: Opportunity,
        factors: list[dict],
        leak_score: int,
    ) -> int:
        unresolved_negative = (await self.db.execute(
            select(func.count(OpportunitySignal.id))
            .where(
                OpportunitySignal.opportunity_id == opp.id,
                OpportunitySignal.is_resolved.is_(False),
                OpportunitySignal.signal_type.in_([
                    "pricing_concern",
                    "competitor",
                    "no_touch",
                    "discount_risk",
                    "sla_breach",
                    "objection",
                ]),
            )
        )).scalar() or 0

        if unresolved_negative > 0:
            factors.append({
                "name": "negative_signals",
                "label": "Olumsuz Sinyaller",
                "detail": f"{unresolved_negative} cozumlenmemis sinyal",
            })
            leak_score += NEGATIVE_SIGNAL_SCORE

        return leak_score
