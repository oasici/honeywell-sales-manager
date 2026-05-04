from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.subscription import Subscription
from app.services.tenant_context import scoped_for_user

logger = logging.getLogger(__name__)

DAYS_IN_MONTH = 30
BILLING_CYCLE_MONTHS = {"monthly": 1, "quarterly": 3, "annual": 12}


class SubscriptionService:
    """Business logic for subscription management.

    Round-4 R4-TEN-7 / R4-SVC-1: every read/write now goes through
    ``scoped_for_user`` so a manager from tenant A can no longer see
    or mutate tenant B's subscriptions, and the MRR dashboard sums
    only the caller's tenant.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_subscriptions(
        self,
        current_user: Any,
        customer_id: int | None = None,
        status: str | None = None,
    ) -> list[Subscription]:
        query = scoped_for_user(
            select(Subscription).order_by(Subscription.created_at.desc()),
            current_user,
            column=Subscription.tenant_id,
        )
        conditions = []
        if customer_id is not None:
            conditions.append(Subscription.customer_id == customer_id)
        if status:
            conditions.append(Subscription.status == status)
        if conditions:
            query = query.where(and_(*conditions))
        result = await self._db.execute(query)
        return list(result.scalars().all())

    async def get_subscription(
        self, sub_id: int, current_user: Any
    ) -> Subscription | None:
        result = await self._db.execute(
            scoped_for_user(
                select(Subscription),
                current_user,
                column=Subscription.tenant_id,
            ).where(Subscription.id == sub_id),
        )
        return result.scalar_one_or_none()

    async def create_subscription(
        self, data: dict, current_user: Any
    ) -> Subscription:
        cycle = data.get("billing_cycle", "monthly")
        start = data.get("start_date", date.today())
        if isinstance(start, str):
            start = date.fromisoformat(start)

        months = BILLING_CYCLE_MONTHS.get(cycle, 1)
        end_date = data.get("end_date")
        if end_date and isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)
        next_renewal = start + timedelta(days=months * DAYS_IN_MONTH)

        sub = Subscription(
            tenant_id=getattr(current_user, "tenant_id", None),
            customer_id=data["customer_id"],
            quote_id=data.get("quote_id"),
            name=data["name"],
            status="active",
            billing_cycle=cycle,
            start_date=start,
            end_date=end_date,
            mrr=float(data.get("mrr", 0)),
            next_renewal_date=next_renewal,
            auto_renew=data.get("auto_renew", True),
            items_json=data.get("items_json"),
            currency=data.get("currency", "TRY"),
            created_by=current_user.id,
        )
        self._db.add(sub)
        await self._db.flush()
        return sub

    async def cancel_subscription(self, sub_id: int, current_user: Any) -> None:
        sub = await self.get_subscription(sub_id, current_user)
        if sub is None:
            return
        sub.status = "cancelled"
        sub.end_date = date.today()
        sub.updated_at = datetime.now(timezone.utc)

    async def renew_subscription(
        self, sub_id: int, current_user: Any
    ) -> Subscription | None:
        sub = await self.get_subscription(sub_id, current_user)
        if sub is None:
            return None
        months = BILLING_CYCLE_MONTHS.get(sub.billing_cycle, 1)
        today = date.today()
        sub.next_renewal_date = today + timedelta(days=months * DAYS_IN_MONTH)
        if sub.end_date and sub.end_date <= today:
            sub.end_date = sub.next_renewal_date
        sub.status = "active"
        sub.updated_at = datetime.now(timezone.utc)
        return sub

    async def get_mrr_dashboard(self, current_user: Any) -> dict:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)

        # Total MRR + active count — tenant-scoped.
        active_q = scoped_for_user(
            select(
                func.coalesce(func.sum(Subscription.mrr), 0).label("total_mrr"),
                func.count(Subscription.id).label("active_count"),
            ),
            current_user,
            column=Subscription.tenant_id,
        ).where(Subscription.status == "active")
        row = (await self._db.execute(active_q)).first()
        total_mrr = float(row.total_mrr) if row else 0
        active_count = int(row.active_count) if row else 0

        # Churned in last 30 days — tenant-scoped.
        churn_q = scoped_for_user(
            select(
                func.count(Subscription.id).label("churn_count"),
                func.coalesce(func.sum(Subscription.mrr), 0).label("churned_mrr"),
            ),
            current_user,
            column=Subscription.tenant_id,
        ).where(
            Subscription.status == "cancelled",
            Subscription.updated_at >= thirty_days_ago,
        )
        churn_row = (await self._db.execute(churn_q)).first()
        churn_count = int(churn_row.churn_count) if churn_row else 0
        churned_mrr = float(churn_row.churned_mrr) if churn_row else 0

        # Top 10 customers by MRR — tenant-scoped on the subscription side
        # which is enough since the customer is implied by the FK.
        top_q = (
            scoped_for_user(
                select(
                    Customer.id,
                    Customer.name,
                    func.sum(Subscription.mrr).label("customer_mrr"),
                ),
                current_user,
                column=Subscription.tenant_id,
            )
            .join(Customer, Subscription.customer_id == Customer.id)
            .where(Subscription.status == "active")
            .group_by(Customer.id, Customer.name)
            .order_by(func.sum(Subscription.mrr).desc())
            .limit(10)
        )
        top_rows = (await self._db.execute(top_q)).all()
        top_customers = [
            {"customer_id": r.id, "name": r.name, "mrr": float(r.customer_mrr)}
            for r in top_rows
        ]

        # Upcoming renewals
        renewals = await self.get_upcoming_renewals(current_user, days=30)
        upcoming_renewals = [
            {
                "id": s.id,
                "name": s.name,
                "customer_id": s.customer_id,
                "next_renewal_date": s.next_renewal_date.isoformat() if s.next_renewal_date else None,
                "mrr": s.mrr,
            }
            for s in renewals
        ]

        return {
            "total_mrr": total_mrr,
            "active_count": active_count,
            "churn_count": churn_count,
            "churned_mrr": churned_mrr,
            "upcoming_renewals": upcoming_renewals,
            "top_customers": top_customers,
        }

    async def get_upcoming_renewals(
        self, current_user: Any, days: int = 30
    ) -> list[Subscription]:
        today = date.today()
        target = today + timedelta(days=days)
        result = await self._db.execute(
            scoped_for_user(
                select(Subscription),
                current_user,
                column=Subscription.tenant_id,
            )
            .where(
                Subscription.status == "active",
                Subscription.next_renewal_date.isnot(None),
                Subscription.next_renewal_date <= target,
            )
            .order_by(Subscription.next_renewal_date),
        )
        return list(result.scalars().all())

    async def auto_renew_due_subscriptions(self) -> int:
        """Auto-renew subscriptions due for renewal.

        Background job; not tenant-scoped because it runs across all
        tenants. The mutation only touches subscriptions with
        ``auto_renew=True`` and is safe across tenant boundaries.
        """
        today = date.today()
        result = await self._db.execute(
            select(Subscription).where(
                Subscription.status == "active",
                Subscription.auto_renew.is_(True),
                Subscription.next_renewal_date.isnot(None),
                Subscription.next_renewal_date <= today,
            ),
        )
        due = result.scalars().all()
        for sub in due:
            months = BILLING_CYCLE_MONTHS.get(sub.billing_cycle, 1)
            sub.next_renewal_date = today + timedelta(days=months * DAYS_IN_MONTH)
            if sub.end_date and sub.end_date <= today:
                sub.end_date = sub.next_renewal_date
            sub.updated_at = datetime.now(timezone.utc)
        return len(due)
