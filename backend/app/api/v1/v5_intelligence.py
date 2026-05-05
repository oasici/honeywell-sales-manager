"""V5 Intelligence Platform endpoints.

Surfaces the V5 services to the rep / manager UI:

* ``GET  /v5/opportunities/{id}/benchmark-gap`` — segment gap envelope
* ``GET  /v5/opportunities/{id}/timing-windows`` — pending timing windows
* ``POST /v5/opportunities/{id}/timing-windows/{window_id}/done``
* ``GET  /v5/opportunities/{id}/objections``
* ``POST /v5/opportunities/{id}/objections/detect``
* ``POST /v5/objections/{id}/resolution``
* ``GET  /v5/opportunities/{id}/similar``
* ``GET  /v5/segments/{key}/dna-recommendations``
* ``GET  /v5/network/anomalies/recent``
* ``GET  /v5/reps/{id}/dna``

Every read is gated by ``FEATURE_V5_INTELLIGENCE`` so the surface
silently 404s when the platform isn't enabled. Auth + RBAC follow the
``decision_gaps`` precedent: reps can only read their own deals.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.user import User
from app.models.v5_network import NetworkAnomaly
from app.models.v5_objection import Objection
from app.models.v5_similarity import RepDnaProfile
from app.core.exceptions import NotFoundException
from app.services import (
    benchmark_gap_service,
    deal_similarity_service,
    dna_pattern_miner,
    objection_intelligence_service,
    timing_engine_service,
)
from app.services.tenant_context import assert_same_tenant
from app.core.rate_limit import (
    enforce_ai_rate_limit as _enforce_ai_rl,
    enforce_tenant_ai_rate_limit as _enforce_tenant_ai_rl,
)


# R5-RL-8 — V5 intelligence services hit Claude (objection mining,
# benchmark gaps); router-level rate limits prevent cost amplification.
router = APIRouter(
    prefix="/v5",
    tags=["V5 Intelligence"],
    dependencies=[Depends(_enforce_tenant_ai_rl), Depends(_enforce_ai_rl)],
)


def _require_v5():
    if not settings.FEATURE_V5_INTELLIGENCE:
        raise HTTPException(status_code=404, detail="Not found")


async def _load_opportunity(
    db: AsyncSession, opp_id: int, current_user: User | None = None
) -> Opportunity:
    """Load Opportunity by id, raising 404 when missing OR cross-tenant.

    R4-TEN-21: every read path that loads an Opportunity by user-supplied
    id must assert tenant equality before returning the row. We map both
    "doesn't exist" and "exists in another tenant" to the same 404 so we
    don't leak which IDs exist in foreign tenants.
    """
    opp = await db.get(Opportunity, opp_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Fırsat bulunamadı")
    if current_user is not None:
        try:
            assert_same_tenant(opp, current_user, exception_cls=NotFoundException)
        except NotFoundException:
            raise HTTPException(status_code=404, detail="Fırsat bulunamadı")
    return opp


def _opp_rbac_guard(current_user: User, opp: Opportunity) -> None:
    if (
        current_user.role == UserRole.SALES_REP.value
        and opp.owner_id is not None
        and int(opp.owner_id) != int(current_user.id)
    ):
        raise HTTPException(status_code=403, detail="Yetkisiz")


def _safe_json_loads(raw: str | None) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


# ─────────────────────── benchmark gap ───────────────────────────────


@router.get("/opportunities/{opportunity_id}/benchmark-gap")
async def get_benchmark_gap(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    opp = await _load_opportunity(db, opportunity_id, current_user)
    _opp_rbac_guard(current_user, opp)
    return await benchmark_gap_service.score_opportunity(db, opportunity_id)


# ─────────────────────── timing engine ───────────────────────────────


@router.get("/opportunities/{opportunity_id}/timing-windows")
async def list_timing_windows(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    opp = await _load_opportunity(db, opportunity_id, current_user)
    _opp_rbac_guard(current_user, opp)
    rows = await timing_engine_service.list_active_windows(
        db, opportunity_id=opportunity_id
    )
    return {
        "opportunity_id": opportunity_id,
        "items": [
            {
                "id": r.id,
                "action_type": r.action_type,
                "window_start": r.window_start.isoformat() if r.window_start else None,
                "window_end": r.window_end.isoformat() if r.window_end else None,
                "urgency_score": r.urgency_score,
                "reason_codes": _safe_json_loads(r.reason_codes_json) or [],
                "status": r.status,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/opportunities/{opportunity_id}/timing-windows/{window_id}/done")
async def mark_timing_window_done(
    opportunity_id: int,
    window_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    opp = await _load_opportunity(db, opportunity_id, current_user)
    _opp_rbac_guard(current_user, opp)
    win = await timing_engine_service.mark_window_done(db, window_id=window_id)
    if win is None:
        raise HTTPException(status_code=404, detail="Window bulunamadı")
    if win.opportunity_id != opportunity_id:
        raise HTTPException(status_code=400, detail="Window/opportunity uyuşmuyor")
    await db.commit()
    return {
        "id": win.id,
        "status": win.status,
        "done_at": win.done_at.isoformat() if win.done_at else None,
    }


# ─────────────────────── objection intelligence ──────────────────────


class DetectObjectionPayload(BaseModel):
    text: str = Field(..., min_length=1, max_length=20_000)
    event_id: int | None = None


@router.get("/opportunities/{opportunity_id}/objections")
async def list_objections(
    opportunity_id: int,
    include_resolved: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    opp = await _load_opportunity(db, opportunity_id, current_user)
    _opp_rbac_guard(current_user, opp)

    stmt = select(Objection).where(Objection.opportunity_id == opportunity_id)
    if not include_resolved:
        stmt = stmt.where(Objection.resolved_flag.is_(False))
    rows = (await db.execute(stmt.order_by(Objection.created_at.desc()))).scalars().all()
    return {
        "opportunity_id": opportunity_id,
        "items": [
            {
                "id": r.id,
                "objection_type": r.objection_type,
                "severity": r.severity,
                "evidence_text": r.evidence_text,
                "resolved_flag": r.resolved_flag,
                "ttr_hours": r.ttr_hours,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/opportunities/{opportunity_id}/objections/detect")
async def detect_objections(
    opportunity_id: int,
    payload: DetectObjectionPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    opp = await _load_opportunity(db, opportunity_id, current_user)
    _opp_rbac_guard(current_user, opp)
    # V7: hybrid path — keyword first, LLM augments when text is long
    # or keyword found nothing. Falls back transparently when the V7
    # flag is off, so single-tenant deployments don't pay Claude cost.
    recorded = await objection_intelligence_service.detect_and_record_hybrid(
        db,
        opportunity_id=opportunity_id,
        text=payload.text,
        event_id=payload.event_id,
    )
    await db.commit()
    return {
        "opportunity_id": opportunity_id,
        "items": [
            {
                "id": o.id,
                "objection_type": o.objection_type,
                "severity": o.severity,
                "evidence_text": o.evidence_text,
            }
            for o in recorded
        ],
        "total": len(recorded),
    }


class ResolutionPayload(BaseModel):
    action_type: str = Field(..., min_length=1, max_length=40)
    payload: dict | None = None
    mark_resolved: bool = False


@router.post("/objections/{objection_id}/resolution")
async def record_resolution(
    objection_id: int,
    payload: ResolutionPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    obj = await db.get(Objection, objection_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Objection bulunamadı")
    # R4-TEN-21: Objection has no tenant_id of its own; chain through the
    # parent Opportunity so cross-tenant probes by objection id surface
    # as 404 indistinguishable from "doesn't exist".
    opp = await _load_opportunity(db, obj.opportunity_id, current_user)
    _opp_rbac_guard(current_user, opp)

    action = await objection_intelligence_service.record_resolution_action(
        db,
        objection_id=objection_id,
        action_type=payload.action_type,
        payload=payload.payload,
        mark_resolved=payload.mark_resolved,
    )
    await db.commit()
    return {
        "id": action.id,
        "objection_id": action.objection_id,
        "action_type": action.action_type,
        "action_ts": action.action_ts.isoformat() if action.action_ts else None,
    }


# ─────────────────────── similarity ──────────────────────────────────


@router.get("/opportunities/{opportunity_id}/similar")
async def list_similar(
    opportunity_id: int,
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    opp = await _load_opportunity(db, opportunity_id, current_user)
    _opp_rbac_guard(current_user, opp)
    items = await deal_similarity_service.list_similar(
        db, opportunity_id=opportunity_id, limit=limit
    )
    return {"opportunity_id": opportunity_id, "items": items, "total": len(items)}


# ─────────────────────── DNA + segment recommendations ───────────────


@router.get("/segments/{segment_key}/dna-recommendations")
async def list_dna_recommendations(
    segment_key: str,
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    if current_user.role not in (
        UserRole.SALES_MANAGER.value,
        UserRole.OPERATIONS.value,
        UserRole.SALES_REP.value,
    ):
        raise HTTPException(status_code=403, detail="Yetkisiz")
    items = await dna_pattern_miner.list_recommendations_for_segment(
        db, segment_key=segment_key, limit=limit
    )
    return {"segment_key": segment_key, "items": items, "total": len(items)}


# ─────────────────────── network anomalies ───────────────────────────


@router.get("/network/anomalies/recent")
async def list_recent_network_anomalies(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    if current_user.role not in (
        UserRole.SALES_MANAGER.value,
        UserRole.OPERATIONS.value,
    ):
        raise HTTPException(status_code=403, detail="Yetkisiz")
    rows = (
        await db.execute(
            select(NetworkAnomaly)
            .where(NetworkAnomaly.resolved_at.is_(None))
            .order_by(NetworkAnomaly.detected_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "segment_key": r.segment_key,
                "metric_name": r.metric_name,
                "expected_value": r.expected_value,
                "actual_value": r.actual_value,
                "z_score": r.z_score,
                "severity": r.severity,
                "explanation": _safe_json_loads(r.explanation_json),
                "detected_at": r.detected_at.isoformat() if r.detected_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


# ─────────────────────── rep DNA ─────────────────────────────────────


@router.get("/reps/{rep_id}/dna")
async def get_rep_dna(
    rep_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v5),
):
    if (
        current_user.role == UserRole.SALES_REP.value
        and int(current_user.id) != rep_id
    ):
        raise HTTPException(status_code=403, detail="Yetkisiz")

    # R4-TEN-21: rep_dna_profiles has no tenant_id; chain through the
    # parent User row. Cross-tenant probes (manager from tenant A asking
    # for tenant B's rep DNA) get the same response shape as "no profile
    # generated yet" so we never leak which user ids exist elsewhere.
    rep_user = await db.get(User, rep_id)
    if rep_user is None:
        return {"rep_id": rep_id, "profile": None}
    try:
        assert_same_tenant(rep_user, current_user, exception_cls=NotFoundException)
    except NotFoundException:
        return {"rep_id": rep_id, "profile": None}

    profile = await db.get(RepDnaProfile, rep_id)
    if profile is None:
        return {"rep_id": rep_id, "profile": None}
    return {
        "rep_id": rep_id,
        "profile": {
            "cluster_label": profile.cluster_label,
            "strengths": _safe_json_loads(profile.strengths_json) or [],
            "gaps": _safe_json_loads(profile.gaps_json) or [],
            "metrics": _safe_json_loads(profile.profile_json),
            "sample_period_start": profile.sample_period_start.isoformat()
            if profile.sample_period_start
            else None,
            "sample_period_end": profile.sample_period_end.isoformat()
            if profile.sample_period_end
            else None,
            "generated_at": profile.generated_at.isoformat()
            if profile.generated_at
            else None,
        },
    }
