"""Slippage dashboard service (V9).

V2 Faz 3.3 #19 — slippage. The data has been there since V4
(``previous_stage`` / ``previous_close_date`` / ``previous_amount``
columns + ``stage_velocity_days`` from V6); V9 just exposes it as a
typed envelope on a dedicated endpoint.

A "slip" is one of:
- close_date pushed forward (current > previous)
- stage regressed (rank current < rank previous)
- amount dropped (current < previous)

Output uses the V5 explainability envelope shape so the frontend can
render it through the same component.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity

logger = logging.getLogger(__name__)


_STAGE_ORDER = (
    "prospecting",
    "qualified",
    "proposal",
    "negotiation",
    "closed_won",
    "closed_lost",
)


def _stage_rank(stage: str | None) -> int:
    if stage is None:
        return -1
    try:
        return _STAGE_ORDER.index(stage)
    except ValueError:
        return -1


@dataclass
class SlipEntry:
    opportunity_id: int
    title: str
    owner_id: int | None
    stage: str
    slip_kinds: list[str] = field(default_factory=list)
    days_pushed: int | None = None
    amount_delta: float | None = None


# ─────────────────────── public envelope ─────────────────────────────


async def slippage_summary(
    db: AsyncSession,
    *,
    owner_id: int | None = None,
    stage: str | None = None,
    window_days: int = 30,
) -> dict:
    """V5-shape envelope: ``{value, confidence, drivers, benchmark_context, recommended_actions}``.

    ``value`` here is the slippage rate (slipped / open) as a percentage
    so dashboards can render it directly.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    conditions = [Opportunity.status == "active", Opportunity.updated_at >= cutoff]
    if owner_id is not None:
        conditions.append(Opportunity.owner_id == owner_id)
    if stage is not None:
        conditions.append(Opportunity.stage == stage)

    rows = (
        await db.execute(select(Opportunity).where(and_(*conditions)))
    ).scalars().all()

    slipped: list[SlipEntry] = []
    for opp in rows:
        kinds: list[str] = []
        days_pushed: int | None = None
        amount_delta: float | None = None

        if (
            opp.previous_close_date is not None
            and opp.close_date is not None
            and opp.close_date > opp.previous_close_date
        ):
            kinds.append("close_date_push")
            days_pushed = (opp.close_date - opp.previous_close_date).days

        if (
            opp.previous_stage
            and _stage_rank(opp.stage) < _stage_rank(opp.previous_stage)
            and _stage_rank(opp.previous_stage) >= 0
        ):
            kinds.append("stage_regression")

        if (
            opp.previous_amount is not None
            and opp.amount is not None
            and opp.amount < opp.previous_amount
        ):
            kinds.append("amount_drop")
            amount_delta = float(opp.amount) - float(opp.previous_amount)

        if kinds:
            slipped.append(
                SlipEntry(
                    opportunity_id=opp.id,
                    title=opp.title,
                    owner_id=opp.owner_id,
                    stage=opp.stage,
                    slip_kinds=kinds,
                    days_pushed=days_pushed,
                    amount_delta=amount_delta,
                )
            )

    total_open = len(rows)
    slipped_count = len(slipped)
    rate = round((slipped_count / total_open) * 100, 2) if total_open else 0.0
    confidence = round(min(1.0, total_open / 20.0), 2)

    # Aggregate drivers — top 3 reasons.
    kind_counts: dict[str, int] = {}
    for s in slipped:
        for k in s.slip_kinds:
            kind_counts[k] = kind_counts.get(k, 0) + 1
    drivers = [
        {
            "label": kind,
            "value": cnt,
            "impact": round(-cnt / max(1, total_open), 3),
        }
        for kind, cnt in sorted(kind_counts.items(), key=lambda kv: -kv[1])[:3]
    ]

    recommended: list[str] = []
    if kind_counts.get("close_date_push", 0) >= 3:
        recommended.append("close_date_push:hard_commit_review")
    if kind_counts.get("stage_regression", 0) >= 1:
        recommended.append("stage_regression:coaching_session")
    if kind_counts.get("amount_drop", 0) >= 2:
        recommended.append("amount_drop:discount_guardrail_audit")

    return {
        "value": rate,
        "confidence": confidence,
        "drivers": drivers,
        "benchmark_context": {
            "open_count": total_open,
            "slipped_count": slipped_count,
            "window_days": window_days,
        },
        "recommended_actions": recommended,
        "items": [
            {
                "opportunity_id": s.opportunity_id,
                "title": s.title,
                "owner_id": s.owner_id,
                "stage": s.stage,
                "slip_kinds": s.slip_kinds,
                "days_pushed": s.days_pushed,
                "amount_delta": s.amount_delta,
            }
            for s in slipped[:50]
        ],
    }


async def slippage_by_owner(
    db: AsyncSession, *, window_days: int = 30
) -> list[dict]:
    """Per-rep slippage rate — feeds the manager coaching dashboard."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    owner_rows = (
        await db.execute(
            select(Opportunity.owner_id, func.count(Opportunity.id))
            .where(Opportunity.status == "active")
            .where(Opportunity.updated_at >= cutoff)
            .group_by(Opportunity.owner_id)
        )
    ).all()
    totals = {int(r[0]): int(r[1]) for r in owner_rows if r[0] is not None}

    out = []
    for owner_id, total in totals.items():
        env = await slippage_summary(
            db, owner_id=owner_id, window_days=window_days
        )
        out.append(
            {
                "owner_id": owner_id,
                "open_count": total,
                "slipped_count": env["benchmark_context"]["slipped_count"],
                "slip_rate_pct": env["value"],
                "top_drivers": env["drivers"],
            }
        )
    out.sort(key=lambda x: -x["slip_rate_pct"])
    return out
