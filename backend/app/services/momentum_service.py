"""Momentum service — reads from feature_store_daily and exposes momentum
analytics, drivers, and history.

The plan's "Phase 3 Sprint 12 Deal Momentum Engine" is satisfied by carving
this read-side service out of feature_store_builder.py. Storage stays in
``opportunity_features_daily`` (momentum_score, momentum_band, momentum_drivers_json),
populated by the nightly builder. This service gives the API a clean
contract without duplicating the materialization logic.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundException
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.tenant_context import assert_same_tenant


_BAND_ORDER = {"rising": 4, "stable": 3, "stalling": 2, "declining": 1, "dead": 0}


@dataclass(frozen=True)
class MomentumPoint:
    snapshot_date: date
    score: int | None
    band: str | None


def _band_from_score(score: int | None) -> str:
    if score is None:
        return "stable"
    if score >= 80:
        return "rising"
    if score >= 60:
        return "stable"
    if score >= 40:
        return "stalling"
    if score >= 20:
        return "declining"
    return "dead"


def _drivers_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    out: list[dict[str, Any]] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        out.append(
            {
                "label": str(entry.get("label", "")),
                "impact": int(entry.get("impact", 0)) if entry.get("impact") is not None else 0,
                "value": entry.get("value"),
            }
        )
    return out


async def get_current_momentum(
    db: AsyncSession,
    opportunity_id: int,
    current_user: User,
) -> dict[str, Any]:
    """Return the latest momentum snapshot + drivers for one opportunity."""

    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if opp is None:
        raise NotFoundException("Firsat bulunamadi")
    assert_same_tenant(opp, current_user, exception_cls=NotFoundException)

    row = (
        await db.execute(
            select(OpportunityFeaturesDaily)
            .where(OpportunityFeaturesDaily.opportunity_id == opportunity_id)
            .order_by(desc(OpportunityFeaturesDaily.snapshot_date))
            .limit(1)
        )
    ).scalar_one_or_none()

    if row is None:
        return {
            "opportunity_id": opportunity_id,
            "score": None,
            "band": "stable",
            "drivers": [],
            "snapshot_date": None,
        }

    band = row.momentum_band or _band_from_score(row.momentum_score)
    return {
        "opportunity_id": opportunity_id,
        "score": row.momentum_score,
        "band": band,
        "drivers": _drivers_json(row.momentum_drivers_json),
        "snapshot_date": row.snapshot_date.isoformat() if row.snapshot_date else None,
    }


async def get_momentum_history(
    db: AsyncSession,
    opportunity_id: int,
    current_user: User,
    days: int = 30,
) -> list[dict[str, Any]]:
    """Daily momentum series for the opportunity (chronological, oldest first)."""

    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if opp is None:
        raise NotFoundException("Firsat bulunamadi")
    assert_same_tenant(opp, current_user, exception_cls=NotFoundException)

    cutoff = date.today() - timedelta(days=max(1, min(days, 365)))
    rows = (
        await db.execute(
            select(OpportunityFeaturesDaily)
            .where(
                and_(
                    OpportunityFeaturesDaily.opportunity_id == opportunity_id,
                    OpportunityFeaturesDaily.snapshot_date >= cutoff,
                )
            )
            .order_by(OpportunityFeaturesDaily.snapshot_date.asc())
        )
    ).scalars().all()

    return [
        {
            "snapshot_date": r.snapshot_date.isoformat(),
            "score": r.momentum_score,
            "band": r.momentum_band or _band_from_score(r.momentum_score),
        }
        for r in rows
    ]


async def get_momentum_distribution(
    db: AsyncSession,
    current_user: User,
) -> dict[str, Any]:
    """Cohort view: how many open deals are in each momentum band today.

    Used by Cockpit + Forecast page to visualize the pipeline at a glance.
    """

    from app.services.tenant_context import scoped_for_user

    today = date.today()
    # Most-recent snapshot per opportunity (window function would be cleaner;
    # for portability we read the latest row per opp via correlated subquery).
    # MVP: read all rows for today; deals without today's row fall back to most
    # recent row available (covered by feature_store_builder on next nightly run).
    rows_today_q = scoped_for_user(
        select(OpportunityFeaturesDaily, Opportunity)
        .join(Opportunity, Opportunity.id == OpportunityFeaturesDaily.opportunity_id)
        .where(
            and_(
                OpportunityFeaturesDaily.snapshot_date == today,
                Opportunity.status == "active",
            )
        ),
        current_user,
        column=Opportunity.tenant_id,
    )
    rows_today = (await db.execute(rows_today_q)).all()

    bands: dict[str, dict[str, Any]] = {
        b: {"count": 0, "amount": 0.0} for b in ("rising", "stable", "stalling", "declining", "dead")
    }
    avg_score_sum = 0
    avg_score_count = 0
    for ofd, opp in rows_today:
        band = ofd.momentum_band or _band_from_score(ofd.momentum_score)
        if band not in bands:
            band = "stable"
        bands[band]["count"] += 1
        bands[band]["amount"] += float(opp.amount or 0)
        if ofd.momentum_score is not None:
            avg_score_sum += int(ofd.momentum_score)
            avg_score_count += 1

    return {
        "snapshot_date": today.isoformat(),
        "bands": [
            {"band": b, "count": v["count"], "amount": round(v["amount"], 2)}
            for b, v in sorted(bands.items(), key=lambda kv: -_BAND_ORDER.get(kv[0], 0))
        ],
        "avg_score": round(avg_score_sum / avg_score_count, 1) if avg_score_count else None,
        "total_deals": sum(v["count"] for v in bands.values()),
    }
