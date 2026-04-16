"""Data quality scoring service — measures completeness of customer and opportunity records."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.opportunity import Opportunity
from app.models.quote import Quote

logger = logging.getLogger(__name__)

CUSTOMER_FIELD_WEIGHTS: dict[str, int] = {
    "name": 10,
    "email": 10,
    "phone": 10,
    "company": 10,
    "address": 10,
    "tax_id": 10,
    "industry": 10,
    "enriched_at": 15,
}

OPPORTUNITY_FIELD_WEIGHTS: dict[str, int] = {
    "amount": 15,
    "close_date": 15,
    "customer_id": 15,
}

OPPORTUNITY_HAS_QUOTES_WEIGHT = 15
OPPORTUNITY_HAS_ACTIVITIES_WEIGHT = 20
OPPORTUNITY_STAGE_MET_WEIGHT = 20

MAX_SCORE = 100
WORST_RECORDS_LIMIT = 10


class DataQualityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def score_customer(self, customer: Customer) -> dict:
        """Score customer data completeness (0-100)."""
        score = 0
        details: list[dict] = []

        for field, weight in CUSTOMER_FIELD_WEIGHTS.items():
            value = getattr(customer, field, None)
            has_value = bool(value)
            if has_value:
                score += weight
            details.append({
                "field": field,
                "weight": weight,
                "completed": has_value,
            })

        opp_count = await self._count_opportunities(customer.id)
        has_opportunity = opp_count > 0
        opportunity_weight = 15
        if has_opportunity:
            score += opportunity_weight
        details.append({
            "field": "has_opportunity",
            "weight": opportunity_weight,
            "completed": has_opportunity,
        })

        return {
            "score": min(score, MAX_SCORE),
            "details": details,
            "total_weight": MAX_SCORE,
        }

    async def score_opportunity(self, opportunity: Opportunity) -> dict:
        """Score opportunity data completeness (0-100)."""
        score = 0
        details: list[dict] = []

        for field, weight in OPPORTUNITY_FIELD_WEIGHTS.items():
            value = getattr(opportunity, field, None)
            has_value = bool(value)
            if has_value:
                score += weight
            details.append({
                "field": field,
                "weight": weight,
                "completed": has_value,
            })

        has_quotes = await self._has_quotes(opportunity.id)
        if has_quotes:
            score += OPPORTUNITY_HAS_QUOTES_WEIGHT
        details.append({
            "field": "has_quotes",
            "weight": OPPORTUNITY_HAS_QUOTES_WEIGHT,
            "completed": has_quotes,
        })

        has_activities = await self._has_activities(opportunity.id)
        if has_activities:
            score += OPPORTUNITY_HAS_ACTIVITIES_WEIGHT
        details.append({
            "field": "has_activities",
            "weight": OPPORTUNITY_HAS_ACTIVITIES_WEIGHT,
            "completed": has_activities,
        })

        is_stage_met = self._check_stage_requirements(opportunity)
        if is_stage_met:
            score += OPPORTUNITY_STAGE_MET_WEIGHT
        details.append({
            "field": "stage_requirements_met",
            "weight": OPPORTUNITY_STAGE_MET_WEIGHT,
            "completed": is_stage_met,
        })

        return {
            "score": min(score, MAX_SCORE),
            "details": details,
            "total_weight": MAX_SCORE,
        }

    async def get_overview(self) -> dict:
        """Overall data quality metrics."""
        customers = (
            await self.db.execute(select(Customer))
        ).scalars().all()

        customer_scores: list[dict] = []
        field_completion: dict[str, dict[str, int]] = {}
        for c in customers:
            result = await self.score_customer(c)
            customer_scores.append({
                "entity_type": "customer",
                "entity_id": c.id,
                "name": c.name,
                "score": result["score"],
            })
            for detail in result["details"]:
                field_name = detail["field"]
                if field_name not in field_completion:
                    field_completion[field_name] = {"total": 0, "completed": 0}
                field_completion[field_name]["total"] += 1
                if detail["completed"]:
                    field_completion[field_name]["completed"] += 1

        opportunities = (
            await self.db.execute(select(Opportunity))
        ).scalars().all()

        opportunity_scores: list[dict] = []
        for o in opportunities:
            result = await self.score_opportunity(o)
            opportunity_scores.append({
                "entity_type": "opportunity",
                "entity_id": o.id,
                "name": o.title,
                "score": result["score"],
            })

        all_scores = customer_scores + opportunity_scores
        avg_customer = (
            sum(s["score"] for s in customer_scores) / len(customer_scores)
            if customer_scores else 0
        )
        avg_opportunity = (
            sum(s["score"] for s in opportunity_scores) / len(opportunity_scores)
            if opportunity_scores else 0
        )
        avg_overall = (
            sum(s["score"] for s in all_scores) / len(all_scores)
            if all_scores else 0
        )

        worst_records = sorted(all_scores, key=lambda x: x["score"])[:WORST_RECORDS_LIMIT]

        field_rates = {
            field: round(
                vals["completed"] / vals["total"] * MAX_SCORE
                if vals["total"] > 0 else 0,
                1,
            )
            for field, vals in field_completion.items()
        }

        return {
            "avg_score": round(avg_overall, 1),
            "avg_customer_score": round(avg_customer, 1),
            "avg_opportunity_score": round(avg_opportunity, 1),
            "total_customers": len(customer_scores),
            "total_opportunities": len(opportunity_scores),
            "worst_records": worst_records,
            "field_completion_rates": field_rates,
        }

    async def _count_opportunities(self, customer_id: int) -> int:
        result = await self.db.execute(
            select(func.count(Opportunity.id)).where(
                Opportunity.customer_id == customer_id,
            )
        )
        return result.scalar() or 0

    async def _has_quotes(self, opportunity_id: int) -> bool:
        result = await self.db.execute(
            select(func.count(Quote.id)).where(
                Quote.opportunity_id == opportunity_id,
            )
        )
        return (result.scalar() or 0) > 0

    async def _has_activities(self, opportunity_id: int) -> bool:
        result = await self.db.execute(
            select(func.count(ActivityLog.id)).where(
                ActivityLog.opportunity_id == opportunity_id,
            )
        )
        return (result.scalar() or 0) > 0

    @staticmethod
    def _check_stage_requirements(opportunity: Opportunity) -> bool:
        """Check if minimal stage requirements are met."""
        stage = opportunity.stage or ""
        if stage in ("prospecting", "qualification"):
            return bool(opportunity.customer_id)
        if stage in ("proposal", "negotiation"):
            return bool(opportunity.amount and opportunity.close_date)
        if stage in ("closed_won", "closed_lost"):
            return bool(
                opportunity.amount
                and opportunity.close_date
                and opportunity.customer_id
            )
        return True
