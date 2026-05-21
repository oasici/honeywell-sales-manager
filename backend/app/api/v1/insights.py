"""Insights endpoints — Sprint 5 (signals, trends, conversation) + later expansions."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.models.enums import OpportunitySignalType
from app.models.opportunity import OpportunitySignal
from app.models.user import User
from app.schemas.round16_aggregates import (
    ConversationInsightsResponse,
    ConversationSearchResponse,
    SignalsDashboardResponse,
    SignalsTrendsResponse,
)

router = APIRouter(prefix="/insights", tags=["Insights"])


def _require_insights():
    # Keep behind board feature flag for now (signals are opportunity-centric).
    if not settings.FEATURE_V2_BOARD:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/signals", response_model=SignalsDashboardResponse)
async def signals_dashboard(
    window: int = Query(30, ge=7, le=365),
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_insights),
):
    """Signals dashboard MVP.

    Output:
    - topic_counts: {pricing_concern, competitor, objection, ...}
    - severity_buckets: {low, med, high}
    - impacted_opportunity_ids: [id, ...]
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window)

    q = (
        select(
            OpportunitySignal.signal_type,
            OpportunitySignal.severity,
            OpportunitySignal.opportunity_id,
            func.count(OpportunitySignal.id).label("cnt"),
        )
        .where(and_(OpportunitySignal.created_at >= cutoff))
        .group_by(
            OpportunitySignal.signal_type,
            OpportunitySignal.severity,
            OpportunitySignal.opportunity_id,
        )
    )

    rows = (await db.execute(q)).all()

    topic_counts: dict[str, int] = {}
    severity_buckets: dict[str, int] = {"low": 0, "med": 0, "high": 0}
    impacted: set[int] = set()

    for signal_type, severity, opp_id, cnt in rows:
        topic_counts[str(signal_type)] = topic_counts.get(str(signal_type), 0) + int(cnt or 0)
        sev = str(severity or "low")
        if sev not in severity_buckets:
            severity_buckets[sev] = 0
        severity_buckets[sev] += int(cnt or 0)
        if opp_id:
            impacted.add(int(opp_id))

    # Provide stable keys even if empty (MVP topics).
    for k in (
        OpportunitySignalType.PRICING_CONCERN.value,
        OpportunitySignalType.COMPETITOR.value,
        OpportunitySignalType.OBJECTION.value,
    ):
        topic_counts.setdefault(k, 0)

    impacted_sorted = sorted(impacted)
    # We cap the embedded id list at 200 to keep the payload light,
    # but emit the unfiltered total + a `has_more` flag so the UI
    # can render "X+ etkilenen fırsat" instead of silently misleading
    # the operator. Callers that need the full list can paginate via
    # the dedicated signals endpoint.
    impacted_total = len(impacted_sorted)
    impacted_returned = impacted_sorted[:200]
    return {
        "window_days": window,
        "topic_counts": topic_counts,
        "severity_buckets": severity_buckets,
        "impacted_opportunity_ids": impacted_returned,
        "impacted_total": impacted_total,
        "impacted_returned": len(impacted_returned),
        "impacted_has_more": impacted_total > len(impacted_returned),
    }


@router.get("/signals/trends", response_model=SignalsTrendsResponse)
async def signals_trends(
    window: int = Query(30, ge=7, le=365),
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_insights),
):
    """Daily signal counts for trend charts."""
    from app.services.conversation_insights_service import signal_trends

    return await signal_trends(db, window_days=window)


@router.get("/conversation-insights", response_model=ConversationInsightsResponse)
async def conversation_insights(
    window: int = Query(30, ge=7, le=365),
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_insights),
):
    """Transcript keyword buckets (pricing / objection / competitor) in the window."""
    from app.services.conversation_insights_service import conversation_insights_keywords

    return await conversation_insights_keywords(db, window_days=window)


@router.get("/conversation-search", response_model=ConversationSearchResponse)
async def conversation_search_endpoint(
    q: str = Query(..., min_length=2, max_length=200),
    stage: str | None = Query(None, max_length=40),
    signal_type: str | None = Query(None, max_length=40),
    owner_id: int | None = Query(None, ge=1),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_insights),
):
    """Search transcripts + linked inbound emails + timeline notes with filters."""
    from app.services.conversation_insights_service import conversation_search

    if current_user.role != UserRole.SALES_MANAGER.value:
        owner_id = None
    return await conversation_search(
        db,
        current_user,
        q=q,
        stage=stage,
        signal_type=signal_type,
        owner_id=owner_id,
        page=page,
        page_size=page_size,
    )

