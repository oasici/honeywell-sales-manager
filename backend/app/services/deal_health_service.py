"""Deal health scoring — computes 0-100 health score per opportunity."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

HEALTHY_THRESHOLD = 70
AT_RISK_THRESHOLD = 40

ACTIVITY_WEIGHT = 0.25
STAGE_VELOCITY_WEIGHT = 0.20
EMAIL_ENGAGEMENT_WEIGHT = 0.15
QUOTE_PROGRESS_WEIGHT = 0.15
TASK_COMPLETION_WEIGHT = 0.10
SIGNAL_BALANCE_WEIGHT = 0.15

ACTIVITY_EXCELLENT_DAYS = 3
ACTIVITY_GOOD_DAYS = 7
ACTIVITY_FAIR_DAYS = 14

EMAIL_EXCELLENT_COUNT = 5
EMAIL_GOOD_COUNT = 3
EMAIL_FAIR_COUNT = 1
EMAIL_LOOKBACK_DAYS = 30

QUOTE_STATUS_SCORES: dict[str, int] = {
    "accepted": 100,
    "sent": 100,
    "approved": 80,
    "pending_approval": 60,
    "draft": 40,
}

MAX_FAILURE_COUNT = 10


@dataclass
class DealIndicator:
    name: str
    label: str
    score: float
    weight: float
    raw_value: float | str
    description: str


@dataclass
class DealHealthReport:
    opportunity_id: int
    title: str
    score: int
    risk_level: str
    indicators: list[DealIndicator] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class DealHealthService:
    """Firsat bazinda saglik skoru hesaplayici."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def compute_deal_health(self, opportunity_id: int) -> DealHealthReport | None:
        """Compute deal health from 6 weighted indicators.

        Returns a DealHealthReport with score (0-100), risk_level, indicators,
        and Turkish recommendations.
        """
        from app.models.opportunity import Opportunity

        result = await self._db.execute(
            select(Opportunity).where(Opportunity.id == opportunity_id)
        )
        opportunity = result.scalar_one_or_none()
        if not opportunity:
            return None

        indicators = [
            await self._activity_recency(opportunity_id),
            await self._stage_velocity(opportunity_id),
            await self._email_engagement(opportunity_id),
            await self._quote_progress(opportunity_id),
            await self._task_completion(opportunity_id),
            await self._signal_balance(opportunity_id),
        ]

        total_weight = sum(i.weight for i in indicators)
        weighted_sum = sum(i.score * i.weight for i in indicators)
        raw_score = weighted_sum / total_weight if total_weight > 0 else 0
        score = max(0, min(100, round(raw_score)))

        risk_level = self._determine_risk_level(score)
        recommendations = self._generate_recommendations(indicators, risk_level)

        return DealHealthReport(
            opportunity_id=opportunity_id,
            title=opportunity.title,
            score=score,
            risk_level=risk_level,
            indicators=indicators,
            recommendations=recommendations,
        )

    async def _activity_recency(self, opp_id: int) -> DealIndicator:
        """Days since last ActivityLog entry.

        0-3d = 100, 3-7 = 75, 7-14 = 50, 14+ = 25, none = 0.
        """
        from app.models.activity_log import ActivityLog

        result = await self._db.execute(
            select(func.max(ActivityLog.created_at))
            .where(ActivityLog.opportunity_id == opp_id)
        )
        last_activity = result.scalar_one_or_none()

        if last_activity is None:
            return DealIndicator(
                name="activity_recency",
                label="Aktivite Guncelligi",
                score=0,
                weight=ACTIVITY_WEIGHT,
                raw_value="yok",
                description="Bu firsat icin hicbir aktivite kaydedilmemis.",
            )

        now = datetime.now(timezone.utc)
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        days_since = (now - last_activity).days

        if days_since <= ACTIVITY_EXCELLENT_DAYS:
            score = 100
        elif days_since <= ACTIVITY_GOOD_DAYS:
            score = 75
        elif days_since <= ACTIVITY_FAIR_DAYS:
            score = 50
        else:
            score = 25

        return DealIndicator(
            name="activity_recency",
            label="Aktivite Guncelligi",
            score=score,
            weight=ACTIVITY_WEIGHT,
            raw_value=days_since,
            description=f"Son aktiviteden bu yana {days_since} gun gecti.",
        )

    async def _stage_velocity(self, opp_id: int) -> DealIndicator:
        """Time in current stage vs average. Faster = higher score."""
        from app.models.opportunity import Opportunity, OpportunityEvent

        result = await self._db.execute(
            select(Opportunity).where(Opportunity.id == opp_id)
        )
        opportunity = result.scalar_one_or_none()
        if not opportunity:
            return DealIndicator(
                name="stage_velocity",
                label="Asama Hizi",
                score=0,
                weight=STAGE_VELOCITY_WEIGHT,
                raw_value="yok",
                description="Firsat bulunamadi.",
            )

        current_stage = opportunity.stage

        # Find when current stage started from stage_change events
        stage_event_result = await self._db.execute(
            select(OpportunityEvent.occurred_at)
            .where(
                OpportunityEvent.opportunity_id == opp_id,
                OpportunityEvent.event_type == "stage_change",
            )
            .order_by(OpportunityEvent.occurred_at.desc())
            .limit(1)
        )
        last_stage_change = stage_event_result.scalar_one_or_none()

        if last_stage_change is None:
            stage_start = opportunity.created_at
        else:
            stage_start = last_stage_change

        now = datetime.now(timezone.utc)
        if stage_start.tzinfo is None:
            stage_start = stage_start.replace(tzinfo=timezone.utc)
        days_in_stage = (now - stage_start).days

        # Compare to average for this stage across all opportunities
        avg_result = await self._db.execute(
            select(func.avg(
                func.extract("epoch", Opportunity.updated_at) / 86400.0
                - func.extract("epoch", Opportunity.created_at) / 86400.0
            ))
            .where(Opportunity.stage == current_stage, Opportunity.id != opp_id)
        )
        avg_days = avg_result.scalar_one_or_none()

        if avg_days is None or avg_days == 0:
            # No comparison data — neutral score
            score = 60
            description = f"{current_stage} asamasinda {days_in_stage} gundur. Karsilastirma verisi yok."
        else:
            ratio = days_in_stage / avg_days
            if ratio <= 0.5:
                score = 100
            elif ratio <= 1.0:
                score = 75
            elif ratio <= 1.5:
                score = 50
            else:
                score = 25
            description = (
                f"{current_stage} asamasinda {days_in_stage} gundur "
                f"(ortalama: {round(avg_days)} gun)."
            )

        return DealIndicator(
            name="stage_velocity",
            label="Asama Hizi",
            score=score,
            weight=STAGE_VELOCITY_WEIGHT,
            raw_value=days_in_stage,
            description=description,
        )

    async def _email_engagement(self, opp_id: int) -> DealIndicator:
        """Email count linked to opportunity in last 30 days."""
        from app.models.email_request import EmailRequest

        cutoff = datetime.now(timezone.utc) - timedelta(days=EMAIL_LOOKBACK_DAYS)
        result = await self._db.execute(
            select(func.count(EmailRequest.id))
            .where(
                EmailRequest.opportunity_id == opp_id,
                EmailRequest.created_at >= cutoff,
            )
        )
        email_count = result.scalar_one() or 0

        if email_count >= EMAIL_EXCELLENT_COUNT:
            score = 100
        elif email_count >= EMAIL_GOOD_COUNT:
            score = 75
        elif email_count >= EMAIL_FAIR_COUNT:
            score = 50
        else:
            score = 25

        return DealIndicator(
            name="email_engagement",
            label="E-posta Etkilesimi",
            score=score,
            weight=EMAIL_ENGAGEMENT_WEIGHT,
            raw_value=email_count,
            description=f"Son {EMAIL_LOOKBACK_DAYS} gunde {email_count} e-posta.",
        )

    async def _quote_progress(self, opp_id: int) -> DealIndicator:
        """Score based on most advanced quote status."""
        from app.models.quote import Quote

        result = await self._db.execute(
            select(Quote.status)
            .where(Quote.opportunity_id == opp_id)
            .order_by(Quote.created_at.desc())
        )
        statuses = [row[0] for row in result.all()]

        if not statuses:
            return DealIndicator(
                name="quote_progress",
                label="Teklif Durumu",
                score=0,
                weight=QUOTE_PROGRESS_WEIGHT,
                raw_value="yok",
                description="Bu firsat icin henuz teklif olusturulmamis.",
            )

        # Find the best (highest-scored) status
        best_score = 0
        best_status = statuses[0]
        for status in statuses:
            status_score = QUOTE_STATUS_SCORES.get(status, 20)
            if status_score > best_score:
                best_score = status_score
                best_status = status

        return DealIndicator(
            name="quote_progress",
            label="Teklif Durumu",
            score=best_score,
            weight=QUOTE_PROGRESS_WEIGHT,
            raw_value=best_status,
            description=f"En ileri teklif durumu: {best_status}.",
        )

    async def _task_completion(self, opp_id: int) -> DealIndicator:
        """Ratio of completed vs total tasks."""
        from app.models.opportunity import Task

        total_result = await self._db.execute(
            select(func.count(Task.id))
            .where(Task.opportunity_id == opp_id)
        )
        total = total_result.scalar_one() or 0

        if total == 0:
            return DealIndicator(
                name="task_completion",
                label="Gorev Tamamlanma",
                score=50,
                weight=TASK_COMPLETION_WEIGHT,
                raw_value="0/0",
                description="Bu firsat icin gorev tanimlanmamis.",
            )

        done_result = await self._db.execute(
            select(func.count(Task.id))
            .where(Task.opportunity_id == opp_id, Task.status == "done")
        )
        done = done_result.scalar_one() or 0

        ratio = done / total
        score = round(ratio * 100)

        return DealIndicator(
            name="task_completion",
            label="Gorev Tamamlanma",
            score=score,
            weight=TASK_COMPLETION_WEIGHT,
            raw_value=f"{done}/{total}",
            description=f"{total} gorevden {done} tanesi tamamlandi.",
        )

    async def _signal_balance(self, opp_id: int) -> DealIndicator:
        """Ratio of positive vs negative signals."""
        from app.models.opportunity import OpportunitySignal

        result = await self._db.execute(
            select(OpportunitySignal.signal_type, OpportunitySignal.is_resolved)
            .where(OpportunitySignal.opportunity_id == opp_id)
        )
        signals = result.all()

        if not signals:
            return DealIndicator(
                name="signal_balance",
                label="Sinyal Dengesi",
                score=50,
                weight=SIGNAL_BALANCE_WEIGHT,
                raw_value="0/0",
                description="Bu firsat icin sinyal kaydedilmemis.",
            )

        positive_count = sum(
            1 for s in signals if s[0] == "positive" or s[1] is True
        )
        negative_count = sum(
            1 for s in signals if s[0] != "positive" and s[1] is not True
        )
        total = positive_count + negative_count

        if total == 0:
            score = 50
        else:
            score = round((positive_count / total) * 100)

        return DealIndicator(
            name="signal_balance",
            label="Sinyal Dengesi",
            score=score,
            weight=SIGNAL_BALANCE_WEIGHT,
            raw_value=f"+{positive_count}/-{negative_count}",
            description=f"{positive_count} olumlu, {negative_count} olumsuz sinyal.",
        )

    def _generate_recommendations(
        self,
        indicators: list[DealIndicator],
        risk_level: str,
    ) -> list[str]:
        """Turkish recommendations based on weak indicators."""
        recommendations: list[str] = []
        indicator_map = {i.name: i for i in indicators}

        activity = indicator_map.get("activity_recency")
        if activity and activity.score < 40:
            recommendations.append(
                "Aktivite cok eski. Musteri ile acil iletisime gecin "
                "veya bir toplanti planlayin."
            )

        velocity = indicator_map.get("stage_velocity")
        if velocity and velocity.score < 40:
            recommendations.append(
                "Firsat bu asamada cok uzun suredir bekliyor. "
                "Ilerlemeyi engelleyen konulari belirleyin."
            )

        email = indicator_map.get("email_engagement")
        if email and email.score < 40:
            recommendations.append(
                "E-posta etkilesimi dusuk. Musteriye takip maili "
                "gonderin veya telefon gorusmesi planlayin."
            )

        quote = indicator_map.get("quote_progress")
        if quote and quote.score < 40:
            recommendations.append(
                "Teklif sureci ilerlemedi. Yeni bir teklif hazirlayarak "
                "musteriye sunun."
            )

        task = indicator_map.get("task_completion")
        if task and task.score < 40:
            recommendations.append(
                "Gorev tamamlanma orani dusuk. Acik gorevleri "
                "onceliklendirin ve tamamlayin."
            )

        signal = indicator_map.get("signal_balance")
        if signal and signal.score < 40:
            recommendations.append(
                "Olumsuz sinyaller agir basiyor. Musteri endiselerini "
                "ele alin ve cozum onerin."
            )

        if risk_level == "critical" and not recommendations:
            recommendations.append(
                "Firsat kritik durumda. Yonetici ile birlikte "
                "kurtarma plani olusturun."
            )

        return recommendations

    async def get_all_deal_health(
        self, owner_id: int | None = None,
    ) -> list[DealHealthReport]:
        """Batch compute for all active opportunities.

        Delegates to the optimized batch method that uses only 6 queries
        total instead of 6*N.
        """
        return await self.get_all_deal_health_batch(owner_id=owner_id)

    async def get_all_deal_health_batch(
        self, owner_id: int | None = None,
    ) -> list[DealHealthReport]:
        """Optimized batch deal health using 6 aggregate queries.

        Instead of calling compute_deal_health() per opportunity (6*N queries),
        this method fetches all indicator data in bulk and computes scores
        in-memory.
        """
        # Check Redis cache first
        cache_key = "deal_health:overview"
        if owner_id is not None:
            cache_key = f"deal_health:overview:owner:{owner_id}"

        cached_reports = await self._read_cache(cache_key)
        if cached_reports is not None:
            return cached_reports

        from app.models.activity_log import ActivityLog
        from app.models.email_request import EmailRequest
        from app.models.opportunity import (
            Opportunity,
            OpportunityEvent,
            OpportunitySignal,
            Task,
        )
        from app.models.quote import Quote

        # 1. Fetch all active opportunities in one query
        query = select(Opportunity).where(Opportunity.status == "active")
        if owner_id is not None:
            query = query.where(Opportunity.owner_id == owner_id)

        result = await self._db.execute(query)
        opportunities = result.scalars().all()

        if not opportunities:
            return []

        opp_ids = [opp.id for opp in opportunities]
        opp_map = {opp.id: opp for opp in opportunities}
        now = datetime.now(timezone.utc)

        # 2. Batch-fetch all indicator data

        # Activity recency: MAX(created_at) per opportunity
        activity_result = await self._db.execute(
            select(
                ActivityLog.opportunity_id,
                func.max(ActivityLog.created_at),
            )
            .where(ActivityLog.opportunity_id.in_(opp_ids))
            .group_by(ActivityLog.opportunity_id)
        )
        activity_map: dict[int, datetime | None] = {
            row[0]: row[1] for row in activity_result.all()
        }

        # Email engagement: COUNT in last 30 days per opportunity
        email_cutoff = now - timedelta(days=EMAIL_LOOKBACK_DAYS)
        email_result = await self._db.execute(
            select(
                EmailRequest.opportunity_id,
                func.count(EmailRequest.id),
            )
            .where(
                EmailRequest.opportunity_id.in_(opp_ids),
                EmailRequest.created_at >= email_cutoff,
            )
            .group_by(EmailRequest.opportunity_id)
        )
        email_map: dict[int, int] = {
            row[0]: row[1] for row in email_result.all()
        }

        # Quote progress: all statuses per opportunity
        quote_result = await self._db.execute(
            select(Quote.opportunity_id, Quote.status)
            .where(Quote.opportunity_id.in_(opp_ids))
        )
        quote_map: dict[int, list[str]] = {}
        for row in quote_result.all():
            quote_map.setdefault(row[0], []).append(row[1])

        # Task completion: COUNT grouped by opportunity_id and status
        task_result = await self._db.execute(
            select(
                Task.opportunity_id,
                Task.status,
                func.count(Task.id),
            )
            .where(Task.opportunity_id.in_(opp_ids))
            .group_by(Task.opportunity_id, Task.status)
        )
        # Build {opp_id: {"done": n, "total": n}}
        task_map: dict[int, dict[str, int]] = {}
        for row in task_result.all():
            opp_id, status, count = row[0], row[1], row[2]
            entry = task_map.setdefault(opp_id, {"done": 0, "total": 0})
            entry["total"] += count
            if status == "done":
                entry["done"] += count

        # Signal balance: signal_type, is_resolved, COUNT per opportunity
        signal_result = await self._db.execute(
            select(
                OpportunitySignal.opportunity_id,
                OpportunitySignal.signal_type,
                OpportunitySignal.is_resolved,
                func.count(OpportunitySignal.id),
            )
            .where(OpportunitySignal.opportunity_id.in_(opp_ids))
            .group_by(
                OpportunitySignal.opportunity_id,
                OpportunitySignal.signal_type,
                OpportunitySignal.is_resolved,
            )
        )
        # Build {opp_id: [(signal_type, is_resolved, count), ...]}
        signal_map: dict[int, list[tuple[str, bool, int]]] = {}
        for row in signal_result.all():
            signal_map.setdefault(row[0], []).append((row[1], row[2], row[3]))

        # Stage velocity: last stage_change event per opportunity
        stage_event_result = await self._db.execute(
            select(
                OpportunityEvent.opportunity_id,
                func.max(OpportunityEvent.occurred_at),
            )
            .where(
                OpportunityEvent.opportunity_id.in_(opp_ids),
                OpportunityEvent.event_type == "stage_change",
            )
            .group_by(OpportunityEvent.opportunity_id)
        )
        stage_event_map: dict[int, datetime] = {
            row[0]: row[1] for row in stage_event_result.all()
        }

        # Stage velocity averages: avg days per stage across all opps
        avg_stage_result = await self._db.execute(
            select(
                Opportunity.stage,
                func.avg(
                    func.extract("epoch", Opportunity.updated_at) / 86400.0
                    - func.extract("epoch", Opportunity.created_at) / 86400.0
                ),
            )
            .where(Opportunity.status == "active")
            .group_by(Opportunity.stage)
        )
        stage_avg_map: dict[str, float] = {
            row[0]: row[1] for row in avg_stage_result.all() if row[1]
        }

        # 3. Compute scores in-memory
        reports: list[DealHealthReport] = []

        for opp in opportunities:
            indicators = [
                self._compute_activity_indicator(opp.id, activity_map, now),
                self._compute_stage_velocity_indicator(
                    opp, stage_event_map, stage_avg_map, now,
                ),
                self._compute_email_indicator(opp.id, email_map),
                self._compute_quote_indicator(opp.id, quote_map),
                self._compute_task_indicator(opp.id, task_map),
                self._compute_signal_indicator(opp.id, signal_map),
            ]

            total_weight = sum(i.weight for i in indicators)
            weighted_sum = sum(i.score * i.weight for i in indicators)
            raw_score = weighted_sum / total_weight if total_weight > 0 else 0
            score = max(0, min(100, round(raw_score)))

            risk_level = self._determine_risk_level(score)
            recommendations = self._generate_recommendations(indicators, risk_level)

            reports.append(
                DealHealthReport(
                    opportunity_id=opp.id,
                    title=opp.title,
                    score=score,
                    risk_level=risk_level,
                    indicators=indicators,
                    recommendations=recommendations,
                )
            )

        reports.sort(key=lambda r: r.score)

        # Write to cache
        await self._write_cache(cache_key, reports)

        return reports

    # ------------------------------------------------------------------
    # In-memory indicator computation helpers (no DB queries)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_activity_indicator(
        opp_id: int,
        activity_map: dict[int, datetime | None],
        now: datetime,
    ) -> DealIndicator:
        last_activity = activity_map.get(opp_id)
        if last_activity is None:
            return DealIndicator(
                name="activity_recency",
                label="Aktivite Guncelligi",
                score=0,
                weight=ACTIVITY_WEIGHT,
                raw_value="yok",
                description="Bu firsat icin hicbir aktivite kaydedilmemis.",
            )

        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        days_since = (now - last_activity).days

        if days_since <= ACTIVITY_EXCELLENT_DAYS:
            score = 100
        elif days_since <= ACTIVITY_GOOD_DAYS:
            score = 75
        elif days_since <= ACTIVITY_FAIR_DAYS:
            score = 50
        else:
            score = 25

        return DealIndicator(
            name="activity_recency",
            label="Aktivite Guncelligi",
            score=score,
            weight=ACTIVITY_WEIGHT,
            raw_value=days_since,
            description=f"Son aktiviteden bu yana {days_since} gun gecti.",
        )

    @staticmethod
    def _compute_stage_velocity_indicator(
        opp: object,
        stage_event_map: dict[int, datetime],
        stage_avg_map: dict[str, float],
        now: datetime,
    ) -> DealIndicator:
        current_stage = opp.stage  # type: ignore[attr-defined]
        opp_id = opp.id  # type: ignore[attr-defined]

        last_stage_change = stage_event_map.get(opp_id)
        if last_stage_change is None:
            stage_start = opp.created_at  # type: ignore[attr-defined]
        else:
            stage_start = last_stage_change

        if stage_start.tzinfo is None:
            stage_start = stage_start.replace(tzinfo=timezone.utc)
        days_in_stage = (now - stage_start).days

        avg_days = stage_avg_map.get(current_stage)

        if avg_days is None or avg_days == 0:
            score = 60
            description = (
                f"{current_stage} asamasinda {days_in_stage} gundur. "
                f"Karsilastirma verisi yok."
            )
        else:
            ratio = days_in_stage / avg_days
            if ratio <= 0.5:
                score = 100
            elif ratio <= 1.0:
                score = 75
            elif ratio <= 1.5:
                score = 50
            else:
                score = 25
            description = (
                f"{current_stage} asamasinda {days_in_stage} gundur "
                f"(ortalama: {round(avg_days)} gun)."
            )

        return DealIndicator(
            name="stage_velocity",
            label="Asama Hizi",
            score=score,
            weight=STAGE_VELOCITY_WEIGHT,
            raw_value=days_in_stage,
            description=description,
        )

    @staticmethod
    def _compute_email_indicator(
        opp_id: int,
        email_map: dict[int, int],
    ) -> DealIndicator:
        email_count = email_map.get(opp_id, 0)

        if email_count >= EMAIL_EXCELLENT_COUNT:
            score = 100
        elif email_count >= EMAIL_GOOD_COUNT:
            score = 75
        elif email_count >= EMAIL_FAIR_COUNT:
            score = 50
        else:
            score = 25

        return DealIndicator(
            name="email_engagement",
            label="E-posta Etkilesimi",
            score=score,
            weight=EMAIL_ENGAGEMENT_WEIGHT,
            raw_value=email_count,
            description=f"Son {EMAIL_LOOKBACK_DAYS} gunde {email_count} e-posta.",
        )

    @staticmethod
    def _compute_quote_indicator(
        opp_id: int,
        quote_map: dict[int, list[str]],
    ) -> DealIndicator:
        statuses = quote_map.get(opp_id, [])

        if not statuses:
            return DealIndicator(
                name="quote_progress",
                label="Teklif Durumu",
                score=0,
                weight=QUOTE_PROGRESS_WEIGHT,
                raw_value="yok",
                description="Bu firsat icin henuz teklif olusturulmamis.",
            )

        best_score = 0
        best_status = statuses[0]
        for status in statuses:
            status_score = QUOTE_STATUS_SCORES.get(status, 20)
            if status_score > best_score:
                best_score = status_score
                best_status = status

        return DealIndicator(
            name="quote_progress",
            label="Teklif Durumu",
            score=best_score,
            weight=QUOTE_PROGRESS_WEIGHT,
            raw_value=best_status,
            description=f"En ileri teklif durumu: {best_status}.",
        )

    @staticmethod
    def _compute_task_indicator(
        opp_id: int,
        task_map: dict[int, dict[str, int]],
    ) -> DealIndicator:
        entry = task_map.get(opp_id)

        if entry is None or entry["total"] == 0:
            return DealIndicator(
                name="task_completion",
                label="Gorev Tamamlanma",
                score=50,
                weight=TASK_COMPLETION_WEIGHT,
                raw_value="0/0",
                description="Bu firsat icin gorev tanimlanmamis.",
            )

        done = entry["done"]
        total = entry["total"]
        ratio = done / total
        score = round(ratio * 100)

        return DealIndicator(
            name="task_completion",
            label="Gorev Tamamlanma",
            score=score,
            weight=TASK_COMPLETION_WEIGHT,
            raw_value=f"{done}/{total}",
            description=f"{total} gorevden {done} tanesi tamamlandi.",
        )

    @staticmethod
    def _compute_signal_indicator(
        opp_id: int,
        signal_map: dict[int, list[tuple[str, bool, int]]],
    ) -> DealIndicator:
        signal_rows = signal_map.get(opp_id, [])

        if not signal_rows:
            return DealIndicator(
                name="signal_balance",
                label="Sinyal Dengesi",
                score=50,
                weight=SIGNAL_BALANCE_WEIGHT,
                raw_value="0/0",
                description="Bu firsat icin sinyal kaydedilmemis.",
            )

        positive_count = 0
        negative_count = 0
        for signal_type, is_resolved, count in signal_rows:
            if signal_type == "positive" or is_resolved is True:
                positive_count += count
            else:
                negative_count += count

        total = positive_count + negative_count
        if total == 0:
            score = 50
        else:
            score = round((positive_count / total) * 100)

        return DealIndicator(
            name="signal_balance",
            label="Sinyal Dengesi",
            score=score,
            weight=SIGNAL_BALANCE_WEIGHT,
            raw_value=f"+{positive_count}/-{negative_count}",
            description=f"{positive_count} olumlu, {negative_count} olumsuz sinyal.",
        )

    # ------------------------------------------------------------------
    # Redis cache helpers
    # ------------------------------------------------------------------

    CACHE_TTL_SECONDS = 300

    @staticmethod
    async def _read_cache(cache_key: str) -> list[DealHealthReport] | None:
        """Read deal health reports from Redis cache."""
        try:
            from app.core.redis_client import get_redis

            redis = get_redis()
            if redis is None:
                return None

            cached_json = await redis.get(cache_key)
            if cached_json is None:
                return None

            raw_list = json.loads(cached_json)
            return [
                DealHealthReport(
                    opportunity_id=item["opportunity_id"],
                    title=item["title"],
                    score=item["score"],
                    risk_level=item["risk_level"],
                    indicators=[
                        DealIndicator(**ind) for ind in item["indicators"]
                    ],
                    recommendations=item["recommendations"],
                )
                for item in raw_list
            ]
        except Exception as exc:
            logger.warning("Redis cache read failed for %s: %s", cache_key, exc)
            return None

    @staticmethod
    async def _write_cache(
        cache_key: str,
        reports: list[DealHealthReport],
    ) -> None:
        """Write deal health reports to Redis with TTL."""
        try:
            from app.core.redis_client import get_redis

            redis = get_redis()
            if redis is None:
                return

            serializable = [asdict(r) for r in reports]
            await redis.set(
                cache_key,
                json.dumps(serializable, default=str),
                ex=DealHealthService.CACHE_TTL_SECONDS,
            )
        except Exception as exc:
            logger.warning("Redis cache write failed for %s: %s", cache_key, exc)

    async def get_at_risk(self, threshold: int = AT_RISK_THRESHOLD) -> list[DealHealthReport]:
        """Opportunities below health threshold."""
        all_reports = await self.get_all_deal_health()
        return [r for r in all_reports if r.score < threshold]

    @staticmethod
    def _determine_risk_level(score: int) -> str:
        if score >= HEALTHY_THRESHOLD:
            return "healthy"
        if score >= AT_RISK_THRESHOLD:
            return "at_risk"
        return "critical"
