from __future__ import annotations

import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.enums import UserRole
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.network_benchmarks import SegmentBenchmarksDaily
from app.models.opportunity import Opportunity
from app.models.user import User


router = APIRouter(prefix="/v4/benchmarks", tags=["V4 Benchmarks"])


def _require_v4():
    if not settings.FEATURE_V4_FEATURE_STORE:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/segments/latest")
async def get_latest_segment_benchmarks(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v4),
):
    if current_user.role not in (UserRole.SALES_MANAGER.value, UserRole.OPERATIONS.value):
        raise HTTPException(status_code=403, detail="Yetkisiz")

    latest_date = (
        await db.execute(select(func.max(SegmentBenchmarksDaily.snapshot_date)))
    ).scalar_one_or_none()
    if not latest_date:
        return {"snapshot_date": None, "items": [], "total": 0}

    rows = (
        await db.execute(
            select(SegmentBenchmarksDaily)
            .where(SegmentBenchmarksDaily.snapshot_date == latest_date)
            .order_by(SegmentBenchmarksDaily.sample_size.desc())
            .limit(limit)
        )
    ).scalars().all()

    return {
        "snapshot_date": latest_date.isoformat(),
        "items": [
            {
                "segment_key": r.segment_key,
                "sample_size": r.sample_size,
                "win_rate_90d": r.win_rate_90d,
                "followup_median_days": r.followup_median_days,
                "avg_discount_pct": r.avg_discount_pct,
                "avg_stakeholder_count": r.avg_stakeholder_count,
                "objection_rate_14d": r.objection_rate_14d,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.get("/opportunities/{opportunity_id}/gap")
async def get_opportunity_benchmark_gap(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v4),
):
    opp = (await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))).scalar_one_or_none()
    if not opp:
        raise HTTPException(status_code=404, detail="Fırsat bulunamadı")
    if current_user.role == UserRole.SALES_REP.value and int(opp.owner_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Yetkisiz")

    latest_date = (
        await db.execute(select(func.max(OpportunityFeaturesDaily.snapshot_date)))
    ).scalar_one_or_none()
    if not latest_date:
        return {"data": None}

    feats = (
        await db.execute(
            select(OpportunityFeaturesDaily)
            .where(
                OpportunityFeaturesDaily.opportunity_id == opportunity_id,
                OpportunityFeaturesDaily.snapshot_date == latest_date,
            )
        )
    ).scalar_one_or_none()
    if not feats:
        return {"data": None}

    segment_key = f"stage:{opp.stage}"
    bench = (
        await db.execute(
            select(SegmentBenchmarksDaily)
            .where(SegmentBenchmarksDaily.segment_key == segment_key, SegmentBenchmarksDaily.snapshot_date == latest_date)
        )
    ).scalar_one_or_none()
    if not bench:
        return {"data": None}

    drivers: list[dict] = []
    gap_score = 50

    # followup gap (higher is worse)
    if bench.followup_median_days is not None:
        delta = float(feats.days_since_last_rep_touch) - float(bench.followup_median_days or 0)
        if delta > 7:
            gap_score -= 15
            drivers.append({"label": "Follow-up gecikiyor", "impact": -15, "value": {"you": feats.days_since_last_rep_touch, "median": bench.followup_median_days}})
        elif delta < -3:
            gap_score += 6
            drivers.append({"label": "Follow-up daha hızlı", "impact": +6, "value": {"you": feats.days_since_last_rep_touch, "median": bench.followup_median_days}})

    # discount gap (higher is worse)
    if feats.latest_discount_pct is not None and bench.avg_discount_pct is not None:
        dd = float(feats.latest_discount_pct) - float(bench.avg_discount_pct)
        if dd > 5:
            gap_score -= 10
            drivers.append({"label": "İskonto segment ortalamasının üstünde", "impact": -10, "value": {"you": feats.latest_discount_pct, "avg": bench.avg_discount_pct}})

    # stakeholder gap (lower is worse) — proxy: use decision gaps already if present; here just compare count placeholder
    # objection rate (presence) — if you have negative signals and segment objection rate is low, penalty
    if bench.objection_rate_14d is not None:
        if (feats.negative_signal_count_14d or 0) > 0 and bench.objection_rate_14d < 0.3:
            gap_score -= 8
            drivers.append({"label": "Negatif sinyal yoğunluğu segment normunun üstünde", "impact": -8, "value": {"you": feats.negative_signal_count_14d, "segment_rate": bench.objection_rate_14d}})

    gap_score = max(0, min(100, int(gap_score)))

    recommended_actions: list[str] = []
    if gap_score < 45:
        recommended_actions.append("Segment benchmark’ına yaklaşmak için 48 saat içinde net next-step + meeting planla")
    if any(d.get("label") == "Follow-up gecikiyor" for d in drivers):
        recommended_actions.append("Bugün follow-up: buyer ile tarih/aksiyon netleştir")

    return {
        "data": {
            "segment_key": segment_key,
            "snapshot_date": latest_date.isoformat(),
            "gap_score": gap_score,
            "drivers": drivers,
            "benchmark_context": {
                "win_rate_90d": bench.win_rate_90d,
                "followup_median_days": bench.followup_median_days,
                "avg_discount_pct": bench.avg_discount_pct,
                "avg_stakeholder_count": bench.avg_stakeholder_count,
                "objection_rate_14d": bench.objection_rate_14d,
                "sample_size": bench.sample_size,
            },
            "you": {
                "days_since_last_rep_touch": feats.days_since_last_rep_touch,
                "latest_discount_pct": feats.latest_discount_pct,
                "negative_signal_count_14d": feats.negative_signal_count_14d,
            },
            "recommended_actions": recommended_actions,
            "model_version": "v4-mvp",
        }
    }

