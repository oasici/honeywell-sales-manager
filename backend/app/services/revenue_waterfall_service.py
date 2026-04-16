"""Revenue Waterfall Service — pipeline movement analysis between two dates."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity, OpportunityEvent

logger = logging.getLogger(__name__)


class RevenueWaterfallService:
    """Calculate pipeline waterfall between two dates."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_waterfall(self, from_date: str, to_date: str) -> dict:
        """Calculate pipeline waterfall between two dates.

        Categories:
        - new: opportunities created in period
        - won: moved to closed_won
        - lost: moved to closed_lost
        - stage_changes: stage transitions in period
        """
        from_dt = datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
        to_dt = datetime.fromisoformat(to_date).replace(tzinfo=timezone.utc)

        categories: list[dict] = []

        # New opportunities created in period
        new_opps = (await self.db.execute(
            select(
                func.count(Opportunity.id),
                func.coalesce(func.sum(Opportunity.amount), 0),
            )
            .where(and_(
                Opportunity.created_at >= from_dt,
                Opportunity.created_at <= to_dt,
            ))
        )).first()
        categories.append({
            "type": "new",
            "label": "Yeni Firsatlar",
            "count": new_opps[0],
            "amount": float(new_opps[1]),
            "positive": True,
        })

        # Won deals in period
        won = (await self.db.execute(
            select(
                func.count(Opportunity.id),
                func.coalesce(func.sum(Opportunity.amount), 0),
            )
            .where(and_(
                Opportunity.stage == "closed_won",
                Opportunity.updated_at >= from_dt,
                Opportunity.updated_at <= to_dt,
            ))
        )).first()
        categories.append({
            "type": "won",
            "label": "Kazanilan",
            "count": won[0],
            "amount": float(won[1]),
            "positive": True,
        })

        # Lost deals in period
        lost = (await self.db.execute(
            select(
                func.count(Opportunity.id),
                func.coalesce(func.sum(Opportunity.amount), 0),
            )
            .where(and_(
                Opportunity.stage == "closed_lost",
                Opportunity.updated_at >= from_dt,
                Opportunity.updated_at <= to_dt,
            ))
        )).first()
        categories.append({
            "type": "lost",
            "label": "Kaybedilen",
            "count": lost[0],
            "amount": float(lost[1]),
            "positive": False,
        })

        # Stage changes in period (from events)
        stage_events = (await self.db.execute(
            select(OpportunityEvent)
            .where(and_(
                OpportunityEvent.event_type == "stage_change",
                OpportunityEvent.occurred_at >= from_dt,
                OpportunityEvent.occurred_at <= to_dt,
            ))
        )).scalars().all()

        categories.append({
            "type": "stage_changes",
            "label": "Asama Degisiklikleri",
            "count": len(stage_events),
            "amount": 0,
            "positive": True,
        })

        # Net change
        net = categories[0]["amount"] + categories[1]["amount"] - categories[2]["amount"]

        return {
            "from_date": from_date,
            "to_date": to_date,
            "categories": categories,
            "net_change": net,
            "total_events": sum(c["count"] for c in categories),
        }
