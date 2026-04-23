"""Rule-based high-intent account scoring (Sprint 4 MVP)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.enums import UserRole
from app.models.opportunity import Opportunity, OpportunitySignal
from app.models.user import User
from app.models.user_customer_pin import UserCustomerPin


TERMINAL = ("closed_won", "closed_lost")


@dataclass(frozen=True)
class HighIntentRow:
    customer_id: int
    name: str
    company: str | None
    score: int
    signals: list[str]
    pinned: bool


class HighIntentService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def _pinned_ids(self, user_id: int) -> set[int]:
        rows = (
            await self._db.execute(
                select(UserCustomerPin.customer_id).where(UserCustomerPin.user_id == user_id)
            )
        ).all()
        return {int(r[0]) for r in rows}

    async def _candidate_customer_ids(self, user: User) -> list[int]:
        if user.role == UserRole.SALES_MANAGER.value:
            q = (
                select(Customer.id)
                .join(Opportunity, Opportunity.customer_id == Customer.id)
                .where(Opportunity.customer_id.isnot(None))
                .distinct()
            )
        else:
            q = (
                select(Customer.id)
                .join(Opportunity, Opportunity.customer_id == Customer.id)
                .where(
                    Opportunity.customer_id.isnot(None),
                    Opportunity.owner_id == user.id,
                )
                .distinct()
            )
        rows = (await self._db.execute(q)).all()
        return [int(r[0]) for r in rows]

    async def _score_customer(self, customer_id: int, now: datetime) -> tuple[int, list[str]]:
        cut7 = now - timedelta(days=7)
        cut30 = now - timedelta(days=30)

        emails_7 = (
            await self._db.execute(
                select(func.count(EmailRequest.id)).where(
                    EmailRequest.customer_id == customer_id,
                    EmailRequest.created_at >= cut7,
                )
            )
        ).scalar() or 0

        act_7 = (
            await self._db.execute(
                select(func.count(ActivityLog.id)).where(
                    ActivityLog.customer_id == customer_id,
                    ActivityLog.created_at >= cut7,
                )
            )
        ).scalar() or 0

        emails_prev = (
            await self._db.execute(
                select(func.count(EmailRequest.id)).where(
                    EmailRequest.customer_id == customer_id,
                    EmailRequest.created_at < cut7,
                    EmailRequest.created_at >= cut30,
                )
            )
        ).scalar() or 0

        open_amt = (
            await self._db.execute(
                select(func.coalesce(func.sum(Opportunity.amount), 0.0)).where(
                    Opportunity.customer_id == customer_id,
                    Opportunity.status == "active",
                    Opportunity.stage.notin_(TERMINAL),
                )
            )
        ).scalar() or 0.0

        opp_ids = (
            await self._db.execute(select(Opportunity.id).where(Opportunity.customer_id == customer_id))
        ).all()
        oid_list = [int(r[0]) for r in opp_ids]
        high_sig = 0
        if oid_list:
            high_sig = (
                await self._db.execute(
                    select(func.count(OpportunitySignal.id)).where(
                        OpportunitySignal.opportunity_id.in_(oid_list),
                        OpportunitySignal.is_resolved.is_(False),
                        OpportunitySignal.severity.in_(("high", "critical")),
                    )
                )
            ).scalar() or 0

        score = 0
        sigs: list[str] = []
        if emails_7 >= 1:
            score += 25
            sigs.append("inbound_email_7d")
        if emails_7 >= 2:
            score += 15
            sigs.append("multi_inbound_7d")
        if act_7 >= 4:
            score += 20
            sigs.append("activity_spike_7d")
        if emails_7 >= 1 and emails_prev == 0:
            score += 15
            sigs.append("inactivity_rebound")
        if float(open_amt) > 0:
            score += 15
            sigs.append("open_pipeline")
        if high_sig > 0:
            score += min(20, 10 + 5 * int(high_sig))
            sigs.append("unresolved_high_signal")

        return min(100, int(score)), sigs

    async def list_high_intent(self, user: User, *, limit: int = 50) -> list[HighIntentRow]:
        now = datetime.now(timezone.utc)
        pinned = await self._pinned_ids(user.id)
        cids = await self._candidate_customer_ids(user)
        rows: list[HighIntentRow] = []

        for cid in cids[:300]:
            sc, sigs = await self._score_customer(cid, now)
            if sc < 25 and cid not in pinned:
                continue
            cust = await self._db.get(Customer, cid)
            if not cust:
                continue
            rows.append(
                HighIntentRow(
                    customer_id=cid,
                    name=cust.name,
                    company=cust.company,
                    score=sc,
                    signals=sigs,
                    pinned=cid in pinned,
                )
            )

        rows.sort(key=lambda r: (not r.pinned, -r.score, r.name))
        return rows[:limit]
