"""Coaching Engine — rep performance scoring based on SOP adherence."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.opportunity import Opportunity, Task
from app.models.quote import Quote
from app.models.user import User

logger = logging.getLogger(__name__)

FOLLOWUP_WEIGHT = 0.25
RESPONSE_SLA_WEIGHT = 0.20
PLAYBOOK_WEIGHT = 0.25
DISCOUNT_WEIGHT = 0.15
ACTIVITY_WEIGHT = 0.15

LOOKBACK_DAYS = 30

RISK_THRESHOLD_LOW = 60
RISK_THRESHOLD_HIGH = 40


@dataclass
class CoachingIndicator:
    name: str
    label: str
    score: float
    weight: float
    raw_value: float | str
    description: str


class CoachingService:
    """Temsilci performans skorlama ve koçluk motoru."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def evaluate_rep(self, user_id: int) -> dict:
        """Compute coaching score (0-100) from 5 indicators.

        Returns a dict with user_id, user_name, score, risk_level,
        indicators list, and Turkish recommendations.
        """
        user = (
            await self._db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if not user:
            return {"error": "Kullanici bulunamadi", "user_id": user_id}

        indicators = [
            await self._followup_adherence(user_id),
            await self._response_sla(user_id),
            await self._playbook_adherence(user_id),
            await self._discount_pattern(user_id),
            await self._activity_frequency(user_id),
        ]

        total_weight = sum(i.weight for i in indicators)
        weighted_sum = sum(i.score * i.weight for i in indicators)
        raw_score = weighted_sum / total_weight if total_weight > 0 else 0
        score = max(0, min(100, round(raw_score)))

        risk_level = self._determine_risk_level(score)
        recommendations = self._generate_recommendations(indicators)

        return {
            "user_id": user_id,
            "user_name": user.full_name,
            "score": score,
            "risk_level": risk_level,
            "indicators": [
                {
                    "name": i.name,
                    "label": i.label,
                    "score": round(i.score, 1),
                    "weight": i.weight,
                    "raw_value": i.raw_value,
                    "description": i.description,
                }
                for i in indicators
            ],
            "recommendations": recommendations,
        }

    async def _followup_adherence(self, user_id: int) -> CoachingIndicator:
        """Overdue tasks / total tasks. Score: 100 if 0% overdue, 0 if >50% overdue."""
        now = datetime.now(timezone.utc)

        total_result = await self._db.execute(
            select(func.count(Task.id)).where(
                Task.owner_id == user_id,
                Task.status == "open",
            )
        )
        total_open = total_result.scalar_one() or 0

        if total_open == 0:
            return CoachingIndicator(
                name="followup_adherence",
                label="Takip Uyumu",
                score=100,
                weight=FOLLOWUP_WEIGHT,
                raw_value="0/0",
                description="Acik gorev bulunmuyor.",
            )

        overdue_result = await self._db.execute(
            select(func.count(Task.id)).where(
                and_(
                    Task.owner_id == user_id,
                    Task.status == "open",
                    Task.due_at < now,
                    Task.due_at.isnot(None),
                )
            )
        )
        overdue = overdue_result.scalar_one() or 0

        overdue_ratio = overdue / total_open
        if overdue_ratio == 0:
            score = 100.0
        elif overdue_ratio <= 0.1:
            score = 85.0
        elif overdue_ratio <= 0.25:
            score = 65.0
        elif overdue_ratio <= 0.5:
            score = 40.0
        else:
            score = 0.0

        return CoachingIndicator(
            name="followup_adherence",
            label="Takip Uyumu",
            score=score,
            weight=FOLLOWUP_WEIGHT,
            raw_value=f"{overdue}/{total_open}",
            description=f"{total_open} acik gorevden {overdue} tanesi gecmis.",
        )

    async def _response_sla(self, user_id: int) -> CoachingIndicator:
        """Average time between email arrival and first task creation on same opportunity.

        Simplified: compare email created_at to first task created_at
        for the same opportunity within lookback period.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

        try:
            from app.models.email_request import EmailRequest
        except ImportError:
            return CoachingIndicator(
                name="response_sla",
                label="Yanit SLA",
                score=60,
                weight=RESPONSE_SLA_WEIGHT,
                raw_value="N/A",
                description="E-posta modeli yuklenemedi.",
            )

        # Get user's opportunities
        opp_ids_result = await self._db.execute(
            select(Opportunity.id).where(Opportunity.owner_id == user_id)
        )
        opp_ids = [row[0] for row in opp_ids_result.all()]

        if not opp_ids:
            return CoachingIndicator(
                name="response_sla",
                label="Yanit SLA",
                score=60,
                weight=RESPONSE_SLA_WEIGHT,
                raw_value="N/A",
                description="Degerlendirme icin firsat bulunamadi.",
            )

        # For each opp, find earliest email and earliest task after cutoff
        email_min = await self._db.execute(
            select(
                EmailRequest.opportunity_id,
                func.min(EmailRequest.created_at),
            )
            .where(
                EmailRequest.opportunity_id.in_(opp_ids),
                EmailRequest.created_at >= cutoff,
            )
            .group_by(EmailRequest.opportunity_id)
        )
        email_map = {row[0]: row[1] for row in email_min.all()}

        task_min = await self._db.execute(
            select(
                Task.opportunity_id,
                func.min(Task.created_at),
            )
            .where(
                Task.opportunity_id.in_(opp_ids),
                Task.created_at >= cutoff,
            )
            .group_by(Task.opportunity_id)
        )
        task_map = {row[0]: row[1] for row in task_min.all()}

        deltas_hours: list[float] = []
        for opp_id in email_map:
            email_ts = email_map[opp_id]
            task_ts = task_map.get(opp_id)
            if task_ts and email_ts:
                if email_ts.tzinfo is None:
                    email_ts = email_ts.replace(tzinfo=timezone.utc)
                if task_ts.tzinfo is None:
                    task_ts = task_ts.replace(tzinfo=timezone.utc)
                delta = (task_ts - email_ts).total_seconds() / 3600.0
                if delta >= 0:
                    deltas_hours.append(delta)

        if not deltas_hours:
            return CoachingIndicator(
                name="response_sla",
                label="Yanit SLA",
                score=60,
                weight=RESPONSE_SLA_WEIGHT,
                raw_value="N/A",
                description="Yeterli veri yok.",
            )

        avg_hours = sum(deltas_hours) / len(deltas_hours)
        if avg_hours <= 4:
            score = 100.0
        elif avg_hours <= 12:
            score = 80.0
        elif avg_hours <= 24:
            score = 60.0
        elif avg_hours <= 48:
            score = 40.0
        else:
            score = 20.0

        return CoachingIndicator(
            name="response_sla",
            label="Yanit SLA",
            score=score,
            weight=RESPONSE_SLA_WEIGHT,
            raw_value=round(avg_hours, 1),
            description=f"Ortalama yanit suresi: {round(avg_hours, 1)} saat.",
        )

    async def _playbook_adherence(self, user_id: int) -> CoachingIndicator:
        """Completed executions / (completed + cancelled) for user's opportunities."""
        try:
            from app.models.playbook import PlaybookExecution
        except (ImportError, ModuleNotFoundError):
            return CoachingIndicator(
                name="playbook_adherence",
                label="Playbook Uyumu",
                score=60,
                weight=PLAYBOOK_WEIGHT,
                raw_value="N/A",
                description="Playbook modulu henuz aktif degil.",
            )

        opp_ids_result = await self._db.execute(
            select(Opportunity.id).where(Opportunity.owner_id == user_id)
        )
        opp_ids = [row[0] for row in opp_ids_result.all()]

        if not opp_ids:
            return CoachingIndicator(
                name="playbook_adherence",
                label="Playbook Uyumu",
                score=60,
                weight=PLAYBOOK_WEIGHT,
                raw_value="N/A",
                description="Firsat bulunamadi.",
            )

        completed_result = await self._db.execute(
            select(func.count(PlaybookExecution.id)).where(
                PlaybookExecution.opportunity_id.in_(opp_ids),
                PlaybookExecution.status == "completed",
            )
        )
        completed = completed_result.scalar_one() or 0

        cancelled_result = await self._db.execute(
            select(func.count(PlaybookExecution.id)).where(
                PlaybookExecution.opportunity_id.in_(opp_ids),
                PlaybookExecution.status == "cancelled",
            )
        )
        cancelled = cancelled_result.scalar_one() or 0

        total = completed + cancelled
        if total == 0:
            return CoachingIndicator(
                name="playbook_adherence",
                label="Playbook Uyumu",
                score=60,
                weight=PLAYBOOK_WEIGHT,
                raw_value="0/0",
                description="Playbook calistirma kaydi yok.",
            )

        ratio = completed / total
        score = round(ratio * 100)

        return CoachingIndicator(
            name="playbook_adherence",
            label="Playbook Uyumu",
            score=score,
            weight=PLAYBOOK_WEIGHT,
            raw_value=f"{completed}/{total}",
            description=f"{total} playbook calistirmasindan {completed} tanesi tamamlandi.",
        )

    async def _discount_pattern(self, user_id: int) -> CoachingIndicator:
        """User's avg discount vs team avg. Score: 100 if <= avg, decreases with deviation."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

        user_result = await self._db.execute(
            select(
                func.avg(Quote.discount_total / func.nullif(Quote.subtotal, 0)),
            ).where(
                Quote.created_by == user_id,
                Quote.created_at >= cutoff,
                Quote.subtotal > 0,
            )
        )
        user_avg = user_result.scalar_one()

        team_result = await self._db.execute(
            select(
                func.avg(Quote.discount_total / func.nullif(Quote.subtotal, 0)),
            ).where(
                Quote.created_at >= cutoff,
                Quote.subtotal > 0,
            )
        )
        team_avg = team_result.scalar_one()

        if user_avg is None or team_avg is None:
            return CoachingIndicator(
                name="discount_pattern",
                label="Indirim Kaliplari",
                score=60,
                weight=DISCOUNT_WEIGHT,
                raw_value="N/A",
                description="Yeterli teklif verisi yok.",
            )

        user_pct = round(user_avg * 100, 1)
        team_pct = round(team_avg * 100, 1)

        if team_avg == 0 or user_avg <= team_avg:
            score = 100.0
        else:
            deviation = (user_avg - team_avg) / team_avg
            if deviation <= 0.1:
                score = 85.0
            elif deviation <= 0.25:
                score = 65.0
            elif deviation <= 0.5:
                score = 40.0
            else:
                score = 20.0

        return CoachingIndicator(
            name="discount_pattern",
            label="Indirim Kaliplari",
            score=score,
            weight=DISCOUNT_WEIGHT,
            raw_value=f"{user_pct}% vs {team_pct}%",
            description=(
                f"Kullanicinin ort. indirimi: %{user_pct}, "
                f"takim ortalamasi: %{team_pct}."
            ),
        )

    async def _activity_frequency(self, user_id: int) -> CoachingIndicator:
        """Activities per active opp vs team avg in last 30 days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

        user_activity_count = (
            await self._db.execute(
                select(func.count(ActivityLog.id)).where(
                    ActivityLog.user_id == user_id,
                    ActivityLog.created_at >= cutoff,
                )
            )
        ).scalar_one() or 0

        user_opp_count = (
            await self._db.execute(
                select(func.count(Opportunity.id)).where(
                    Opportunity.owner_id == user_id,
                    Opportunity.status == "active",
                )
            )
        ).scalar_one() or 0

        if user_opp_count == 0:
            user_ratio = 0.0
        else:
            user_ratio = user_activity_count / user_opp_count

        # Team average
        team_activity_count = (
            await self._db.execute(
                select(func.count(ActivityLog.id)).where(
                    ActivityLog.created_at >= cutoff,
                )
            )
        ).scalar_one() or 0

        team_opp_count = (
            await self._db.execute(
                select(func.count(Opportunity.id)).where(
                    Opportunity.status == "active",
                )
            )
        ).scalar_one() or 0

        if team_opp_count == 0:
            team_ratio = 0.0
        else:
            team_ratio = team_activity_count / team_opp_count

        if team_ratio == 0:
            score = 60.0
        elif user_ratio >= team_ratio:
            score = 100.0
        elif user_ratio >= team_ratio * 0.75:
            score = 75.0
        elif user_ratio >= team_ratio * 0.5:
            score = 50.0
        else:
            score = 25.0

        return CoachingIndicator(
            name="activity_frequency",
            label="Aktivite Sikligi",
            score=score,
            weight=ACTIVITY_WEIGHT,
            raw_value=f"{round(user_ratio, 1)} vs {round(team_ratio, 1)}",
            description=(
                f"Firsat basina {round(user_ratio, 1)} aktivite "
                f"(takim ort.: {round(team_ratio, 1)})."
            ),
        )

    async def evaluate_all_reps(self) -> list[dict]:
        """Batch evaluate all active sales reps."""
        users = (
            await self._db.execute(
                select(User).where(
                    User.is_active.is_(True),
                    User.role.in_(["sales_rep", "sales_manager"]),
                )
            )
        ).scalars().all()

        results = []
        for user in users:
            try:
                result = await self.evaluate_rep(user.id)
                results.append(result)
            except Exception as exc:
                logger.warning(
                    "Coaching evaluation failed for user %d: %s",
                    user.id,
                    exc,
                )

        results.sort(key=lambda r: r.get("score", 0))
        return results

    def _generate_recommendations(self, indicators: list[CoachingIndicator]) -> list[str]:
        """Turkish recommendations for weak indicators."""
        recommendations: list[str] = []
        indicator_map = {i.name: i for i in indicators}

        followup = indicator_map.get("followup_adherence")
        if followup and followup.score < 50:
            recommendations.append(
                "Gecmis gorevleriniz fazla. Acik gorevleri onceliklendirin "
                "ve zamaninda tamamlayin."
            )

        response = indicator_map.get("response_sla")
        if response and response.score < 50:
            recommendations.append(
                "E-postalara yanit sureniz yuksek. Gelen taleplere "
                "4 saat icinde donmeyi hedefleyin."
            )

        playbook = indicator_map.get("playbook_adherence")
        if playbook and playbook.score < 50:
            recommendations.append(
                "Playbook tamamlama oraniniz dusuk. Satis sureclerini "
                "playbook adimlarina gore yonetin."
            )

        discount = indicator_map.get("discount_pattern")
        if discount and discount.score < 50:
            recommendations.append(
                "Indirim oraniniz takim ortalamasinin ustunde. "
                "Deger odakli satis tekniklerini uygulayarak "
                "indirim oranini azaltin."
            )

        activity = indicator_map.get("activity_frequency")
        if activity and activity.score < 50:
            recommendations.append(
                "Aktivite sikliginiz dusuk. Her firsat icin duzeli "
                "temas ve takip plani olusturun."
            )

        return recommendations

    @staticmethod
    def _determine_risk_level(score: int) -> str:
        if score >= RISK_THRESHOLD_LOW:
            return "healthy"
        if score >= RISK_THRESHOLD_HIGH:
            return "needs_improvement"
        return "at_risk"
