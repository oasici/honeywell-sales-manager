from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.intelligence.additive.projectors import (
    opportunity_signal_to_conversation_view,
    revenue_signal_to_conversation_view,
)
from app.intelligence.additive.timeline_query import load_merged_canonical_timeline
from app.models.enums import UserRole
from app.models.opportunity import Opportunity, OpportunitySignal
from app.models.revenue_signal import RevenueSignal
from app.models.sales_event_shadow import SalesEventShadow
from app.models.user import User
from app.schemas.common import ItemsResponse


router = APIRouter(prefix="/v4/alignment", tags=["V4 Additive Alignment"])


def _require_readmodel():
    if not settings.FEATURE_V4_ADDITIVE_READMODEL:
        raise HTTPException(status_code=404, detail="Not found")


def _require_shadow_table():
    if not settings.FEATURE_V4_SALES_EVENTS_SHADOW:
        raise HTTPException(status_code=404, detail="Not found")


class ShadowBackfillBody(BaseModel):
    """Manual backfill window length (rolling from now, UTC)."""

    days: int = Field(default=7, ge=1, le=365)


@router.post("/shadow/sync-window", response_model=dict)
async def shadow_sync_manual_backfill(
    body: ShadowBackfillBody,
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_shadow_table),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER, UserRole.OPERATIONS)),
):
    """Manager/operations: materialize shadow rows for the last ``days`` (idempotent)."""
    from app.services.sales_events_shadow_sync import sync_sales_events_shadow_last_n_days

    counts = await sync_sales_events_shadow_last_n_days(db, days=body.days)
    return {"ok": True, "window_days": body.days, "counts": counts}


@router.get("/opportunities/{opportunity_id}/normalized-timeline", response_model=ItemsResponse)
async def normalized_sales_event_timeline(
    opportunity_id: int,
    limit: int = Query(300, ge=1, le=1000),
    include_legacy_opportunity_signals: bool = Query(
        False,
        description="Include legacy opportunity_signals rows as canonical timeline entries.",
    ),
    include_signals: bool = Query(
        True,
        description="Merge revenue_signals as synthetic timeline rows (conversation signal feed).",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_readmodel),
):
    """Read-only union of activity_logs + opportunity_events (+ optional revenue_signals) in target shape."""
    # V13 cross-tenant guard before RBAC
    from app.core.exceptions import NotFoundException
    from app.services.tenant_context import load_with_tenant_check

    try:
        opp = await load_with_tenant_check(
            db,
            Opportunity,
            opportunity_id,
            current_user=current_user,
            exception_cls=NotFoundException,
            message="Fırsat bulunamadı",
        )
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Fırsat bulunamadı")
    if current_user.role == UserRole.SALES_REP.value and int(opp.owner_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Yetkisiz")

    account_id = int(opp.customer_id) if opp.customer_id else None

    merged = await load_merged_canonical_timeline(
        db,
        opportunity_id,
        account_id=account_id,
        limit=limit,
        include_signals=include_signals,
        include_legacy_opportunity_signals=include_legacy_opportunity_signals,
    )

    return {
        "opportunity_id": opportunity_id,
        "account_id": account_id,
        "model_version": "v4-additive-readmodel",
        "include_signals": include_signals,
        "include_legacy_opportunity_signals": include_legacy_opportunity_signals,
        "items": [m.model_dump() for m in merged],
        "total": len(merged),
    }


@router.get("/opportunities/{opportunity_id}/conversation-signals", response_model=ItemsResponse)
async def conversation_signals_projection(
    opportunity_id: int,
    limit: int = Query(200, ge=1, le=1000),
    include_legacy_opportunity_signals: bool = Query(
        True,
        description="Merge legacy opportunity_signals into the same response (sorted by time).",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_readmodel),
):
    """Unified read: ``revenue_signals`` + optional legacy ``opportunity_signals`` in one list."""
    # V13 cross-tenant guard before RBAC
    from app.core.exceptions import NotFoundException
    from app.services.tenant_context import load_with_tenant_check

    try:
        opp = await load_with_tenant_check(
            db,
            Opportunity,
            opportunity_id,
            current_user=current_user,
            exception_cls=NotFoundException,
            message="Fırsat bulunamadı",
        )
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Fırsat bulunamadı")
    if current_user.role == UserRole.SALES_REP.value and int(opp.owner_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Yetkisiz")

    account_id = int(opp.customer_id) if opp.customer_id else None

    sig_rows = (
        await db.execute(
            select(RevenueSignal)
            .where(RevenueSignal.opportunity_id == opportunity_id)
            .order_by(RevenueSignal.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()

    rev_views = [revenue_signal_to_conversation_view(r) for r in sig_rows]
    merged_views = list(rev_views)

    if include_legacy_opportunity_signals:
        legacy_rows = (
            await db.execute(
                select(OpportunitySignal)
                .where(OpportunitySignal.opportunity_id == opportunity_id)
                .order_by(OpportunitySignal.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        merged_views.extend(
            [opportunity_signal_to_conversation_view(s, account_id=account_id) for s in legacy_rows]
        )

    merged_views.sort(key=lambda v: v.created_at, reverse=True)
    merged_views = merged_views[:limit]

    return {
        "opportunity_id": opportunity_id,
        "account_id": account_id,
        "model_version": "v4-additive-readmodel",
        "include_legacy_opportunity_signals": include_legacy_opportunity_signals,
        "items": [i.model_dump() for i in merged_views],
        "total": len(merged_views),
    }


@router.get("/opportunities/{opportunity_id}/shadow-timeline", response_model=ItemsResponse)
async def shadow_sales_events_timeline(
    opportunity_id: int,
    limit: int = Query(500, ge=1, le=2000),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_shadow_table),
):
    """Rows from ``v4_sales_events_shadow`` (nightly sync). Live projection remains under /normalized-timeline."""
    # V13 cross-tenant guard before RBAC
    from app.core.exceptions import NotFoundException
    from app.services.tenant_context import load_with_tenant_check

    try:
        opp = await load_with_tenant_check(
            db,
            Opportunity,
            opportunity_id,
            current_user=current_user,
            exception_cls=NotFoundException,
            message="Fırsat bulunamadı",
        )
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Fırsat bulunamadı")
    if current_user.role == UserRole.SALES_REP.value and int(opp.owner_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Yetkisiz")

    rows = (
        await db.execute(
            select(SalesEventShadow)
            .where(SalesEventShadow.opportunity_id == opportunity_id)
            .order_by(SalesEventShadow.event_ts.asc())
            .limit(limit)
        )
    ).scalars().all()

    items = []
    for r in rows:
        try:
            payload = json.loads(r.payload_json or "{}")
        except json.JSONDecodeError:
            payload = {}
        items.append(
            {
                "source_ref": r.source_ref,
                "provenance": r.provenance,
                "account_id": r.account_id,
                "opportunity_id": r.opportunity_id,
                "contact_id": r.contact_id,
                "event_type": r.event_type,
                "event_ts": r.event_ts.isoformat() if r.event_ts else None,
                "actor_type": r.actor_type,
                "actor_id": r.actor_id,
                "channel": r.channel,
                "direction": r.direction,
                "payload_json": payload,
                "synced_at": r.synced_at.isoformat() if r.synced_at else None,
            }
        )

    return {
        "opportunity_id": opportunity_id,
        "model_version": "v4-sales-events-shadow",
        "items": items,
        "total": len(items),
    }
