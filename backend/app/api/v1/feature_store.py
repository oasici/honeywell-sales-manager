from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import NotFoundException
from app.models.enums import UserRole
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services.feature_store_builder import build_daily_feature_store
from app.services.tenant_context import assert_same_tenant


router = APIRouter(prefix="/v4", tags=["V4 Feature Store"])


def _require_v4_feature_store():
    if not settings.FEATURE_V4_FEATURE_STORE:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/feature-store/build", response_model=dict)
async def build_feature_store(
    snapshot_date: date | None = Query(default=None),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v4_feature_store),
):
    """Build daily snapshots (idempotent). Manager/Ops only."""
    result = await build_daily_feature_store(db, snapshot_date=snapshot_date)
    return {
        "snapshot_date": result.snapshot_date.isoformat(),
        "opportunities_upserted": result.opportunities_upserted,
        "accounts_upserted": result.accounts_upserted,
        "reps_upserted": result.reps_upserted,
    }


@router.get("/opportunities/{opportunity_id}/features/latest", response_model=dict)
async def get_latest_opportunity_features(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v4_feature_store),
):
    """Read latest feature snapshot for an opportunity (rep-scoped by existing RBAC at opp layer)."""
    # R5-TEN-26 — feature snapshots inherit tenant from the parent opp;
    # the "RBAC at opp layer" comment was promising a check that wasn't
    # actually performed at this endpoint. Load opp + assert_same_tenant.
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
            .order_by(OpportunityFeaturesDaily.snapshot_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if not row:
        return {"data": None}

    # ``momentum_drivers_json`` is the column name for what is logically
    # a list of driver objects (each with label, contribution, weight).
    # The previous version returned the raw JSON string, which forced
    # every consumer to JSON.parse() on the client. Deserialise here so
    # the API contract is "rich list of driver dicts" and the column
    # name stays an implementation detail.
    import json as _json

    drivers: list = []
    if row.momentum_drivers_json:
        try:
            parsed = _json.loads(row.momentum_drivers_json)
            if isinstance(parsed, list):
                drivers = parsed
        except Exception:
            # Malformed payload — log nothing here (the daily build job
            # is the right place to alert on bad writes); just emit an
            # empty list so the UI degrades gracefully.
            drivers = []

    return {
        "data": {
            "opportunity_id": row.opportunity_id,
            "snapshot_date": row.snapshot_date.isoformat(),
            "deal_age_days": row.deal_age_days,
            "days_since_last_rep_touch": row.days_since_last_rep_touch,
            "days_since_last_buyer_touch": row.days_since_last_buyer_touch,
            "rep_touch_count_14d": row.rep_touch_count_14d,
            "buyer_reply_count_14d": row.buyer_reply_count_14d,
            "meeting_count_30d": row.meeting_count_30d,
            "quote_count": row.quote_count,
            "latest_discount_pct": row.latest_discount_pct,
            "competitor_mentions_30d": row.competitor_mentions_30d,
            "pricing_objections_30d": row.pricing_objections_30d,
            "positive_signal_count_14d": row.positive_signal_count_14d,
            "negative_signal_count_14d": row.negative_signal_count_14d,
            "momentum_score": row.momentum_score,
            "momentum_band": row.momentum_band,
            # Keep the raw column for any back-compat consumer; surface
            # the parsed list under ``momentum_drivers`` so new UI
            # callers don't need to JSON.parse client-side.
            "momentum_drivers_json": row.momentum_drivers_json,
            "momentum_drivers": drivers,
            "buyer_state": row.buyer_state,
            "close_probability": row.close_probability,
            # V6 trajectory fields if present on the row — these are
            # surfaced for the deal-health card to render trajectory
            # arrows alongside the headline momentum score.
            "stage_velocity_days": getattr(row, "stage_velocity_days", None),
            "objection_density_norm": getattr(row, "objection_density_norm", None),
        }
    }

