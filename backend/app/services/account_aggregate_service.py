"""Sprint 3 — Account-level rollups, Account360 assembly, meeting-prep context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.models.account_enrichment import AccountEnrichment
from app.models.activity_log import ActivityLog
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.enums import UserRole
from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal
from app.models.user import User


TERMINAL_STAGES = ("closed_won", "closed_lost")

STALE_SECONDS = 15 * 60


@dataclass(frozen=True)
class LastTouch:
    at: datetime | None
    source: str
    summary: str


def _opp_conditions(customer_id: int, user: User) -> list:
    conds = [Opportunity.customer_id == customer_id]
    if user.role == UserRole.SALES_REP.value:
        conds.append(Opportunity.owner_id == user.id)
    return conds


class AccountAggregateService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_enrichment_row(self, customer_id: int) -> AccountEnrichment | None:
        return (
            await self._db.execute(
                select(AccountEnrichment).where(AccountEnrichment.customer_id == customer_id)
            )
        ).scalar_one_or_none()

    def _is_stale(self, row: AccountEnrichment | None) -> bool:
        if row is None or row.computed_at is None:
            return True
        now = datetime.now(timezone.utc)
        ca = row.computed_at
        if ca.tzinfo is None:
            ca = ca.replace(tzinfo=timezone.utc)
        return (now - ca).total_seconds() > STALE_SECONDS

    async def ensure_fresh(
        self, customer_id: int, user: User, *, refresh: bool = False
    ) -> AccountEnrichment:
        row = await self.get_enrichment_row(customer_id)
        if refresh or self._is_stale(row):
            return await self.refresh_enrichment(customer_id, user)
        assert row is not None
        return row

    async def infer_display_currency(
        self,
        customer_id: int,
        active_pipeline: list[Opportunity],
        all_opps: list[Opportunity],
    ) -> str:
        """Prefer newest active-pipeline deal currency; else any opp; else latest quote; else TRY."""
        from app.models.quote import Quote

        def _opp_ts(o: Opportunity) -> datetime:
            for x in (o.updated_at, o.created_at):
                if x is not None:
                    return x if x.tzinfo else x.replace(tzinfo=timezone.utc)
            return datetime.min.replace(tzinfo=timezone.utc)

        if active_pipeline:
            pick = max(active_pipeline, key=_opp_ts)
            c = (pick.currency or "TRY").strip()
            return c or "TRY"
        if all_opps:
            pick = max(all_opps, key=_opp_ts)
            c = (pick.currency or "TRY").strip()
            return c or "TRY"

        cur = (
            await self._db.execute(
                select(Quote.currency)
                .where(Quote.customer_id == customer_id)
                .order_by(Quote.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if cur and str(cur).strip():
            return str(cur).strip()
        return "TRY"

    async def refresh_enrichment(self, customer_id: int, user: User) -> AccountEnrichment:
        """Compute metrics and upsert account_enrichments."""
        from app.services.customer_health_service import CustomerHealthService

        base = and_(*_opp_conditions(customer_id, user))

        all_opps = (
            await self._db.execute(select(Opportunity).where(base))
        ).scalars().all()

        won = [o for o in all_opps if o.stage == "closed_won"]
        lost = [o for o in all_opps if o.stage == "closed_lost"]
        active_pipeline = [
            o
            for o in all_opps
            if o.status == "active" and o.stage not in TERMINAL_STAGES
        ]

        pipeline_open_amount = sum(float(o.amount or 0) for o in active_pipeline)
        closed_won_revenue = sum(float(o.amount or 0) for o in won)
        display_currency = await self.infer_display_currency(customer_id, active_pipeline, all_opps)

        health = await CustomerHealthService(self._db).calculate_health_score(customer_id)
        health_score = float(health.score) if health else 50.0
        risk_index = max(0.0, min(100.0, 100.0 - health_score))

        engagement_score = 50.0
        if health:
            for ind in health.indicators:
                if ind.name == "engagement_recency":
                    engagement_score = max(0.0, min(100.0, float(ind.score)))
                    break

        last_touch = await self._compute_last_touch(customer_id, [o.id for o in all_opps])

        row = await self.get_enrichment_row(customer_id)
        now = datetime.now(timezone.utc)
        payload = dict(
            pipeline_open_amount=pipeline_open_amount,
            closed_won_revenue=closed_won_revenue,
            active_deal_count=len(active_pipeline),
            won_deal_count=len(won),
            lost_deal_count=len(lost),
            total_deal_count=len(all_opps),
            risk_index=risk_index,
            engagement_score=engagement_score,
            last_touch_at=last_touch.at,
            computed_at=now,
            extra={
                "health_score": int(health_score) if health else None,
                "health_risk_level": health.risk_level if health else None,
                "last_touch_source": last_touch.source,
                "last_touch_summary": last_touch.summary,
                "display_currency": display_currency,
            },
        )
        if row is None:
            row = AccountEnrichment(customer_id=customer_id, **payload)
            self._db.add(row)
        else:
            for k, v in payload.items():
                setattr(row, k, v)
        await self._db.flush()
        await self._db.refresh(row)
        return row

    async def _compute_last_touch(self, customer_id: int, opp_ids: list[int]) -> LastTouch:
        candidates: list[tuple[datetime, str, str]] = []

        eq = await self._db.execute(
            select(func.max(EmailRequest.created_at)).where(EmailRequest.customer_id == customer_id)
        )
        em_ts = eq.scalar()
        if em_ts is not None:
            ts = em_ts if em_ts.tzinfo else em_ts.replace(tzinfo=timezone.utc)
            candidates.append((ts, "email", "Son gelen e-posta aktivitesi"))

        if opp_ids:
            aq = await self._db.execute(
                select(func.max(ActivityLog.created_at)).where(
                    or_(
                        ActivityLog.customer_id == customer_id,
                        ActivityLog.opportunity_id.in_(opp_ids),
                    )
                )
            )
            al_ts = aq.scalar()
            if al_ts is not None:
                ts = al_ts if al_ts.tzinfo else al_ts.replace(tzinfo=timezone.utc)
                candidates.append((ts, "activity", "Son CRM aktivitesi"))

            oq = await self._db.execute(
                select(func.max(Opportunity.updated_at)).where(Opportunity.id.in_(opp_ids))
            )
            ou_ts = oq.scalar()
            if ou_ts is not None:
                ts = ou_ts if ou_ts.tzinfo else ou_ts.replace(tzinfo=timezone.utc)
                candidates.append((ts, "opportunity", "Firsat kaydinda son guncelleme"))

        if not candidates:
            return LastTouch(at=None, source="none", summary="Kayitli son temas bulunamadi")
        best = max(candidates, key=lambda x: x[0])
        return LastTouch(at=best[0], source=best[1], summary=best[2])

    async def merge_multi_opportunity_timeline(
        self,
        customer_id: int,
        user: User,
        limit: int = 40,
    ) -> list[dict]:
        base = and_(*_opp_conditions(customer_id, user))
        opps = (await self._db.execute(select(Opportunity).where(base))).scalars().all()
        opp_ids = [int(o.id) for o in opps]
        if not opp_ids:
            return []

        ev_rows = (
            await self._db.execute(
                select(OpportunityEvent, Opportunity.title)
                .join(Opportunity, Opportunity.id == OpportunityEvent.opportunity_id)
                .where(OpportunityEvent.opportunity_id.in_(opp_ids))
                .order_by(OpportunityEvent.occurred_at.desc())
                .limit(80)
            )
        ).all()

        merged: list[dict] = []
        for ev, opp_title in ev_rows:
            merged.append(
                {
                    "kind": "opportunity_event",
                    "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
                    "opportunity_id": ev.opportunity_id,
                    "opportunity_title": opp_title,
                    "event_type": ev.event_type,
                    "entity_type": ev.entity_type,
                    "entity_id": ev.entity_id,
                    "description": ev.description,
                }
            )

        # `defer(source_ref)` keeps the column out of the SELECT list —
        # see api/v1/activities.py for the schema-drift rationale.
        log_rows = (
            await self._db.execute(
                select(ActivityLog)
                .options(defer(ActivityLog.source_ref))
                .where(
                    or_(
                        ActivityLog.customer_id == customer_id,
                        ActivityLog.opportunity_id.in_(opp_ids),
                    )
                )
                .order_by(ActivityLog.created_at.desc())
                .limit(80)
            )
        ).scalars().all()

        for a in log_rows:
            merged.append(
                {
                    "kind": "activity",
                    "occurred_at": a.created_at.isoformat() if a.created_at else None,
                    "opportunity_id": a.opportunity_id,
                    "opportunity_title": None,
                    "event_type": a.activity_type,
                    "entity_type": a.entity_type,
                    "entity_id": a.entity_id,
                    "description": a.summary,
                }
            )

        merged.sort(key=lambda r: r.get("occurred_at") or "", reverse=True)
        return merged[:limit]

    async def open_deals(self, customer_id: int, user: User) -> list[dict]:
        base = and_(
            *_opp_conditions(customer_id, user),
            Opportunity.status == "active",
            Opportunity.stage.notin_(TERMINAL_STAGES),
        )
        rows = (
            await self._db.execute(
                select(Opportunity).where(base).order_by(Opportunity.updated_at.desc()).limit(50)
            )
        ).scalars().all()
        return [
            {
                "id": o.id,
                "title": o.title,
                "stage": o.stage,
                "amount": o.amount,
                "currency": o.currency,
                "owner_id": o.owner_id,
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            }
            for o in rows
        ]

    async def risk_summary(self, customer_id: int, user: User) -> dict:
        from app.services.customer_health_service import CustomerHealthService

        report = await CustomerHealthService(self._db).calculate_health_score(customer_id)
        base = and_(*_opp_conditions(customer_id, user))
        id_rows = (await self._db.execute(select(Opportunity.id).where(base))).all()
        opp_ids = [int(r[0]) for r in id_rows]

        high_unresolved = 0
        if opp_ids:
            high_unresolved = (
                await self._db.execute(
                    select(func.count(OpportunitySignal.id)).where(
                        OpportunitySignal.opportunity_id.in_(opp_ids),
                        OpportunitySignal.is_resolved.is_(False),
                        OpportunitySignal.severity.in_(("high", "critical")),
                    )
                )
            ).scalar() or 0

        row = await self.get_enrichment_row(customer_id)
        return {
            "health_score": report.score if report else None,
            "risk_level": report.risk_level if report else "unknown",
            "risk_index": float(row.risk_index) if row else None,
            "unresolved_high_signals": int(high_unresolved),
            "recommendations": (report.recommendations[:5] if report else []),
        }

    async def build_meeting_prep_context(self, customer_id: int, user: User) -> str:
        """Plain-text context for LLM (PII redacted at API boundary)."""
        cust = (
            await self._db.execute(select(Customer).where(Customer.id == customer_id))
        ).scalar_one_or_none()
        if not cust:
            return ""

        row = await self.get_enrichment_row(customer_id)
        if row is None or self._is_stale(row):
            row = await self.refresh_enrichment(customer_id, user)

        opens = await self.open_deals(customer_id, user)
        risk = await self.risk_summary(customer_id, user)
        lines = [
            f"Musteri: {cust.name}",
            f"Sirket: {cust.company or '-'}",
            "",
            "Hesap ozeti (onbellek):",
            f"- Acik pipeline tutari: {row.pipeline_open_amount}",
            f"- Kazanilan (closed_won) ciro: {row.closed_won_revenue}",
            f"- Acik firsat sayisi: {row.active_deal_count}",
            f"- Risk indeksi (0-100, yuksek=kotu): {row.risk_index}",
            f"- Etkilesim skoru (0-100): {row.engagement_score}",
            "",
            "Acik firsatlar:",
        ]
        for o in opens[:12]:
            lines.append(f"  - {o['title']} | asama={o['stage']} | tutar={o.get('amount')}")
        lines.append("")
        lines.append("Risk ozeti:")
        lines.append(f"  Saglik skoru: {risk.get('health_score')}")
        lines.append(f"  Risk seviyesi: {risk.get('risk_level')}")
        lines.append(f"  Cozulmemis yuksek sinyal: {risk.get('unresolved_high_signals')}")
        for rec in (risk.get("recommendations") or [])[:4]:
            lines.append(f"  - {rec}")
        return "\n".join(lines)
