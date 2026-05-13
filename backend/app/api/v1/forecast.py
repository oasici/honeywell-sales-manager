"""Forecast adjustments and pipeline snapshot API."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.models.forecast import ForecastAdjustment, PipelineSnapshot
from app.models.user import User
from app.services.forecast_service import ForecastService
from app.services.tenant_context import scoped_for_user
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/forecast", tags=["Forecast"])


def _require_forecast():
    """Dependency: reject if FEATURE_V2_BOARD is off (forecast is part of board)."""
    if not settings.FEATURE_V2_BOARD:
        raise HTTPException(status_code=404, detail="Not found")


# -- Pydantic Schemas --

class AdjustmentCreate(BaseModel):
    opportunity_id: int
    new_amount: float | None = None
    new_category: str | None = None
    reason: str | None = None


# ══════════════════════════════════════════
# Hybrid Forecast (Sprint 5.4)
# ══════════════════════════════════════════

@router.get("/hybrid")
async def get_hybrid_forecast(
    owner_id: int | None = Query(None, description="Rep owner filter (manager only)"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_forecast),
):
    """Return both legacy stage-weighted forecast and new hybrid weighted forecast.

    - legacy_weighted: amount * stage_probability(stage)
    - hybrid_weighted: amount * close_probability (heuristic predictive scoring)
    """
    from app.models.opportunity import Opportunity
    from app.services.forecast_service import _get_stage_probabilities
    from app.services.predictive_scoring_service import predict_close_probability

    stage_prob = await _get_stage_probabilities(db)

    conditions = [Opportunity.status == "active"]
    if owner_id is not None:
        conditions.append(Opportunity.owner_id == owner_id)

    # Round-4 R4-TEN-17 — scope hybrid forecast to the caller's tenant.
    hybrid_query = scoped_for_user(
        select(Opportunity).where(and_(*conditions)),
        current_user,
        column=Opportunity.tenant_id,
    )
    opps = (await db.execute(hybrid_query)).scalars().all()

    legacy_total = 0.0
    hybrid_total = 0.0

    by_stage: dict[str, dict] = {}
    by_confidence: dict[str, dict] = {"low": {"count": 0, "amount": 0.0, "hybrid_weighted": 0.0},
                                      "medium": {"count": 0, "amount": 0.0, "hybrid_weighted": 0.0},
                                      "high": {"count": 0, "amount": 0.0, "hybrid_weighted": 0.0}}

    for opp in opps:
        amount = float(opp.amount or 0.0)
        stage_p = float(stage_prob.get(opp.stage, 0.0))
        legacy_weighted = amount * stage_p
        legacy_total += legacy_weighted

        pred = await predict_close_probability(db, opp.id)
        close_p = float(pred.get("close_probability") or 0.0)
        conf = str(pred.get("confidence_band") or "low")
        if conf not in by_confidence:
            conf = "low"

        hybrid_weighted = amount * close_p
        hybrid_total += hybrid_weighted

        if opp.stage not in by_stage:
            by_stage[opp.stage] = {"stage": opp.stage, "count": 0, "amount": 0.0, "legacy_weighted": 0.0, "hybrid_weighted": 0.0}
        by_stage[opp.stage]["count"] += 1
        by_stage[opp.stage]["amount"] += amount
        by_stage[opp.stage]["legacy_weighted"] += legacy_weighted
        by_stage[opp.stage]["hybrid_weighted"] += hybrid_weighted

        by_confidence[conf]["count"] += 1
        by_confidence[conf]["amount"] += amount
        by_confidence[conf]["hybrid_weighted"] += hybrid_weighted

    stages = sorted(by_stage.values(), key=lambda s: s["stage"])

    def _round_block(x: dict) -> dict:
        return {
            **x,
            "amount": round(float(x.get("amount", 0.0)), 2),
            "legacy_weighted": round(float(x.get("legacy_weighted", 0.0)), 2),
            "hybrid_weighted": round(float(x.get("hybrid_weighted", 0.0)), 2),
        }

    return {
        "owner_id": owner_id,
        "legacy_weighted_total": round(legacy_total, 2),
        "hybrid_weighted_total": round(hybrid_total, 2),
        "by_stage": [_round_block(s) for s in stages],
        "by_confidence": {
            k: {"count": v["count"], "amount": round(v["amount"], 2), "hybrid_weighted": round(v["hybrid_weighted"], 2)}
            for k, v in by_confidence.items()
        },
    }


# -- Adjustment Endpoints --

@router.post("/adjustments", status_code=201)
async def create_adjustment(
    data: AdjustmentCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_forecast),
):
    """Create a forecast adjustment (manager only).

    Round-14 R14-AUTH-1 — ``current_user`` is threaded into the service
    so the underlying opportunity tenant boundary is enforced before
    the mutation lands. Pre-fix, a tenant A manager could mutate any
    tenant B opportunity's forecast by knowing the id.
    """
    service = ForecastService(db)
    adjustment = await service.create_adjustment(
        opp_id=data.opportunity_id,
        user_id=current_user.id,
        new_amount=data.new_amount,
        new_category=data.new_category,
        reason=data.reason,
        current_user=current_user,
    )
    return _adjustment_to_dict(adjustment)


@router.get("/adjustments", response_model=PaginatedResponse[dict])
async def list_adjustments(
    opportunity_id: int = Query(..., ge=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_forecast),
):
    """Get adjustment history for an opportunity.

    Round-14 R14-AUTH-1 — verify the opportunity belongs to the
    caller's tenant before disclosing adjustment history. Pre-fix,
    any tenant could read any other tenant's adjustment trail.
    """
    service = ForecastService(db)
    adjustments = await service.get_adjustments(
        opportunity_id, current_user=current_user
    )
    items = [_adjustment_to_dict(a) for a in adjustments]
    total = len(items)
    # R6-PAGE-1 — canonical envelope.
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
    }


# -- Snapshot Endpoints --

@router.get("/snapshots", response_model=PaginatedResponse[dict])
async def list_snapshots(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_forecast),
):
    """Get pipeline snapshots (manager only)."""
    service = ForecastService(db)
    snapshots = await service.get_snapshots(start_date=start_date, end_date=end_date)
    items = [_snapshot_to_dict(s) for s in snapshots]
    total = len(items)
    # R6-PAGE-1 — canonical envelope.
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
    }


@router.post("/snapshot", status_code=201)
async def take_snapshot(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_forecast),
):
    """Manually trigger a pipeline snapshot (manager only)."""
    service = ForecastService(db)
    snapshots = await service.take_pipeline_snapshot()
    return {"items": [_snapshot_to_dict(s) for s in snapshots]}


@router.get("/wow")
async def week_over_week(
    weeks: int = Query(4, ge=1, le=12),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_forecast),
):
    """Get week-over-week pipeline comparison.

    Returns shape expected by frontend WoWData:
    {weeks: [{week_label, total}], current_total, previous_total, delta, delta_pct}
    """
    service = ForecastService(db)
    raw = await service.get_week_over_week(weeks=weeks)

    # Reverse so oldest week is first (chronological order for chart)
    raw.reverse()

    chart_weeks = []
    for entry in raw:
        ws = entry.get("week_start", "")
        we = entry.get("week_end", "")
        label = f"{ws[5:10]} - {we[5:10]}" if ws and we else ""
        chart_weeks.append({
            "week_label": label,
            "total": round(entry.get("total_amount", 0), 2),
        })

    current_total = chart_weeks[-1]["total"] if chart_weeks else 0
    previous_total = chart_weeks[-2]["total"] if len(chart_weeks) >= 2 else 0
    delta = round(current_total - previous_total, 2)
    delta_pct = round((delta / previous_total * 100) if previous_total else 0, 1)

    return {
        "weeks": chart_weeks,
        "current_total": current_total,
        "previous_total": previous_total,
        "delta": delta,
        "delta_pct": delta_pct,
    }


@router.get("/team-rollup")
async def team_forecast_rollup(
    manager_id: int | None = Query(None, description="Filter to reps managed by this user"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_forecast),
):
    """Forecast rollup by rep — manager view of team pipeline."""
    service = ForecastService(db)
    return await service.get_team_forecast(manager_id=manager_id)


# -- Forecast Accuracy (Modul 12) --

@router.get("/accuracy")
async def get_forecast_accuracy(
    quarter: str | None = Query(None, description="Quarter in YYYY-QN format, e.g. 2026-Q1"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_forecast),
):
    """Compare forecast predictions vs actual outcomes for a period."""
    from app.models.forecast_snapshot_detail import ForecastSnapshotDetail
    from app.models.opportunity import Opportunity

    # Determine period boundaries
    now = datetime.now(timezone.utc)
    if quarter:
        try:
            year_str, q_str = quarter.split("-Q")
            year = int(year_str)
            q = int(q_str)
            period_start = datetime(year, (q - 1) * 3 + 1, 1, tzinfo=timezone.utc)
            if q == 4:
                period_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                period_end = datetime(year, q * 3 + 1, 1, tzinfo=timezone.utc)
        except (ValueError, IndexError):
            period_start = now - timedelta(days=90)
            period_end = now
    else:
        period_start = now - timedelta(days=90)
        period_end = now

    period_label = quarter or f"{period_start.date()} - {period_end.date()}"

    # Round-4 R4-TEN-17 — accuracy must only see the caller's tenant pipeline.
    won_query = scoped_for_user(
        select(Opportunity).where(
            and_(
                Opportunity.stage == "closed_won",
                Opportunity.updated_at >= period_start,
                Opportunity.updated_at < period_end,
            )
        ),
        current_user,
        column=Opportunity.tenant_id,
    )
    won_opps_q = await db.execute(won_query)
    won_opps = won_opps_q.scalars().all()
    actual_won = sum(float(o.amount or 0) for o in won_opps)

    # Get earliest snapshot detail for these opportunities in the period.
    # ``won_opp_ids`` is now derived from a tenant-scoped query, so the
    # IN-clause downstream cannot cross the tenant boundary either.
    won_opp_ids = [o.id for o in won_opps]
    commit_forecast = 0.0
    per_rep: dict[int, dict] = {}
    first_snapshot: dict[int, ForecastSnapshotDetail] = {}

    if won_opp_ids:
        # Find snapshot details from start of period for these opps
        snapshot_details_q = await db.execute(
            select(ForecastSnapshotDetail)
            .where(
                and_(
                    ForecastSnapshotDetail.opportunity_id.in_(won_opp_ids),
                    ForecastSnapshotDetail.created_at >= period_start,
                    ForecastSnapshotDetail.created_at < period_end,
                )
            )
            .order_by(ForecastSnapshotDetail.created_at.asc())
        )
        snapshot_details = snapshot_details_q.scalars().all()

        # Take first snapshot per opportunity (earliest prediction)
        for sd in snapshot_details:
            if sd.opportunity_id not in first_snapshot:
                first_snapshot[sd.opportunity_id] = sd

        commit_forecast = sum(float(sd.amount) for sd in first_snapshot.values())

    # Build per-rep breakdown
    for opp in won_opps:
        owner_id = opp.owner_id
        if owner_id not in per_rep:
            per_rep[owner_id] = {
                "user_id": owner_id,
                "user_name": "",
                "forecast": 0.0,
                "actual": 0.0,
            }
        per_rep[owner_id]["actual"] += float(opp.amount or 0)
        if opp.id in first_snapshot:
            per_rep[owner_id]["forecast"] += float(first_snapshot[opp.id].amount)

    # Enrich with user names
    if per_rep:
        from app.models.user import User as UserModel
        users_q = await db.execute(
            select(UserModel.id, UserModel.full_name).where(
                UserModel.id.in_(list(per_rep.keys()))
            )
        )
        for u in users_q.all():
            if u.id in per_rep:
                per_rep[u.id]["user_name"] = u.full_name

    # Calculate accuracy for each rep
    per_rep_list = []
    for rep_data in per_rep.values():
        if rep_data["forecast"] > 0:
            accuracy = round(
                min(rep_data["actual"], rep_data["forecast"]) / rep_data["forecast"] * 100,
                1,
            )
        else:
            accuracy = 0.0
        per_rep_list.append({**rep_data, "accuracy": accuracy})

    # Overall accuracy
    accuracy_pct = (
        round(min(actual_won, commit_forecast) / commit_forecast * 100, 1)
        if commit_forecast > 0
        else 0.0
    )

    return {
        "period": period_label,
        "commit_forecast": round(commit_forecast, 2),
        "actual_won": round(actual_won, 2),
        "accuracy_pct": accuracy_pct,
        "per_rep": per_rep_list,
    }


# -- Helpers --

def _adjustment_to_dict(adj: ForecastAdjustment) -> dict:
    return {
        "id": adj.id,
        "opportunity_id": adj.opportunity_id,
        "adjusted_by": adj.adjusted_by,
        "original_amount": adj.original_amount,
        "adjusted_amount": adj.adjusted_amount,
        "original_category": adj.original_category,
        "adjusted_category": adj.adjusted_category,
        "reason": adj.reason,
        "created_at": adj.created_at.isoformat() if adj.created_at else None,
    }


def _snapshot_to_dict(snap: PipelineSnapshot) -> dict:
    return {
        "id": snap.id,
        "snapshot_date": snap.snapshot_date.isoformat() if snap.snapshot_date else None,
        "stage": snap.stage,
        "opportunity_count": snap.opportunity_count,
        "total_amount": snap.total_amount,
        "weighted_amount": snap.weighted_amount,
        "created_at": snap.created_at.isoformat() if snap.created_at else None,
    }
