"""V9 — V2/V3 gap closure endpoints.

Routes mounted under ``/api/v1/v9/``:

* CRM Sync (Sprint K)
* Calendar OAuth + meeting auto-log (Sprint L)
* Board WIP + pipeline review queue (Sprint M)
* NL semantic search (Sprint N)
* Quote revisions (Sprint O)
* Slippage dashboard (Sprint P)

Each surface is gated behind the appropriate feature flag so a tenant
can opt into individual capabilities.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.enums import UserRole
from app.models.opportunity import Opportunity
from app.models.user import User
from app.models.v9_board_ux import PipelineReviewQueueEntry
from app.models.v9_calendar import CalendarConnection, MeetingAutoLink
from app.models.v9_crm_sync import CrmConnection, CrmSyncJob
from app.services import (
    calendar_sync_service,
    nl_search_service,
    pipeline_review_service,
    quote_revision_service,
    slippage_service,
)
from app.services.crm_sync import run_sync_job
from app.services.crm_sync.factory import get_adapter
from app.services.tenant_context import assert_same_tenant
from app.schemas.v9_gap_closure import (
    BoardWipStatusResponse,
    CalendarConnectionResponse,
    CalendarConnectionsListResponse,
    CrmConnectionCreatedResponse,
    CrmConnectionTestResponse,
    CrmConnectionsListResponse,
    CrmJobsListResponse,
    CrmSyncJobResponse,
    MeetingAutoLinkResponse,
    QuoteRevisionsResponse,
    ReviewDecideResponse,
    ReviewQueueResponse,
    ReviseQuoteResponse,
    SemanticSearchResponse,
    SlippageByOwnerResponse,
    SlippageEnvelope,
)


router = APIRouter(prefix="/v9", tags=["V9 Gap Closure"])


# ─────────────────────── flag guards ─────────────────────────────────


def _require_crm_sync():
    if not getattr(settings, "FEATURE_V9_CRM_SYNC", False):
        raise HTTPException(status_code=404, detail="Not found")


def _require_calendar():
    if not getattr(settings, "FEATURE_V9_CALENDAR_OAUTH", False):
        raise HTTPException(status_code=404, detail="Not found")


def _require_nl_search():
    if not getattr(settings, "FEATURE_V9_NL_SEARCH", False):
        raise HTTPException(status_code=404, detail="Not found")


def _require_v2_board():
    if not settings.FEATURE_V2_BOARD:
        raise HTTPException(status_code=404, detail="Not found")


def _manager_only(current_user: User) -> None:
    if current_user.role not in (
        UserRole.SALES_MANAGER.value,
        UserRole.OPERATIONS.value,
    ):
        raise HTTPException(status_code=403, detail="Yetkisiz")


# ─────────────────────── Sprint K: CRM Sync ──────────────────────────


class CrmConnectionPayload(BaseModel):
    provider: str = Field(..., min_length=1, max_length=40)
    label: str = Field(..., min_length=1, max_length=120)
    base_url: str | None = None
    credentials: dict[str, Any] | None = None


@router.post("/crm/connections", response_model=CrmConnectionCreatedResponse)
async def create_crm_connection(
    payload: CrmConnectionPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_crm_sync),
):
    _manager_only(current_user)
    if payload.provider.lower() not in {"salesforce", "hubspot"}:
        raise HTTPException(status_code=400, detail="Unsupported provider")
    conn = CrmConnection(
        tenant_id=getattr(current_user, "tenant_id", None),
        provider=payload.provider.lower(),
        label=payload.label,
        base_url=payload.base_url,
        credentials_json=json.dumps(payload.credentials or {}),
        is_active=False,
        sync_state="idle",
        created_by=current_user.id,
    )
    db.add(conn)
    await db.flush()
    await db.commit()
    return {
        "id": conn.id,
        "provider": conn.provider,
        "label": conn.label,
        "is_active": conn.is_active,
    }


@router.get("/crm/connections", response_model=CrmConnectionsListResponse)
async def list_crm_connections(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_crm_sync),
):
    _manager_only(current_user)
    rows = (
        await db.execute(select(CrmConnection).order_by(CrmConnection.created_at.desc()))
    ).scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "provider": r.provider,
                "label": r.label,
                "is_active": r.is_active,
                "sync_state": r.sync_state,
                "last_sync_at": r.last_sync_at.isoformat() if r.last_sync_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/crm/connections/{conn_id}/test", response_model=CrmConnectionTestResponse)
async def test_crm_connection(
    conn_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_crm_sync),
):
    _manager_only(current_user)
    conn = await db.get(CrmConnection, conn_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Bağlantı bulunamadı")
    adapter = get_adapter(conn, test_mode=True)
    creds = json.loads(conn.credentials_json or "{}")
    ok = adapter.test_credentials(creds)
    return {"ok": bool(ok), "provider": conn.provider}


@router.post("/crm/connections/{conn_id}/sync/{entity_type}", response_model=CrmSyncJobResponse)
async def trigger_crm_sync(
    conn_id: int,
    entity_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_crm_sync),
):
    _manager_only(current_user)
    if entity_type not in {"account", "opportunity"}:
        raise HTTPException(status_code=400, detail="Unsupported entity_type")
    job = await run_sync_job(
        db, connection_id=conn_id, entity_type=entity_type, test_mode=True
    )
    await db.commit()
    return {
        "id": job.id,
        "status": job.status,
        "items_pulled": job.items_pulled,
        "items_failed": job.items_failed,
    }


@router.get("/crm/jobs", response_model=CrmJobsListResponse)
async def list_crm_jobs(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_crm_sync),
):
    _manager_only(current_user)
    rows = (
        await db.execute(
            select(CrmSyncJob).order_by(CrmSyncJob.created_at.desc()).limit(limit)
        )
    ).scalars().all()
    return {
        "items": [
            {
                "id": r.id,
                "connection_id": r.connection_id,
                "entity_type": r.entity_type,
                "status": r.status,
                "items_pulled": r.items_pulled,
                "items_failed": r.items_failed,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


# ─────────────────────── Sprint L: Calendar OAuth ────────────────────


class CalendarLinkPayload(BaseModel):
    provider: str = Field(..., min_length=1, max_length=40)
    calendar_id: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None


@router.post("/calendar/connect", response_model=CalendarConnectionResponse)
async def connect_calendar(
    payload: CalendarLinkPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_calendar),
):
    if payload.provider.lower() not in {"google", "microsoft"}:
        raise HTTPException(status_code=400, detail="Unsupported calendar provider")
    conn = await calendar_sync_service.upsert_calendar_connection(
        db,
        user_id=current_user.id,
        provider=payload.provider.lower(),
        calendar_id=payload.calendar_id,
        access_token=payload.access_token,
        refresh_token=payload.refresh_token,
    )
    await db.commit()
    return {
        "id": conn.id,
        "provider": conn.provider,
        "is_active": conn.is_active,
    }


@router.get("/calendar/connections", response_model=CalendarConnectionsListResponse)
async def list_calendar_conns(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_calendar),
):
    rows = await calendar_sync_service.list_calendar_connections(
        db, user_id=current_user.id
    )
    return {
        "items": [
            {
                "id": r.id,
                "provider": r.provider,
                "calendar_id": r.calendar_id,
                "is_active": r.is_active,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


@router.post("/calendar/auto-log/{booking_id}", response_model=MeetingAutoLinkResponse)
async def auto_log_booking(
    booking_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_calendar),
):
    link = await calendar_sync_service.auto_log_meeting(db, meeting_booking_id=booking_id)
    await db.commit()
    if link is None:
        raise HTTPException(status_code=404, detail="Booking bulunamadı veya eşleşmedi")
    return {
        "id": link.id,
        "opportunity_id": link.opportunity_id,
        "matched_by": link.matched_by,
        "confidence": link.confidence,
    }


# ─────────────────────── Sprint M: WIP + review queue ────────────────


@router.get("/board/wip-status", response_model=BoardWipStatusResponse)
async def board_wip_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    return {"items": await pipeline_review_service.wip_status(db)}


@router.get("/board/review-queue", response_model=ReviewQueueResponse)
async def board_review_queue(
    owner_id: int | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    # Reps see only their own queue; managers see all unless they
    # passed an explicit owner_id.
    effective_owner = owner_id
    if current_user.role == UserRole.SALES_REP.value:
        effective_owner = current_user.id

    rows = await pipeline_review_service.list_pending_suggestions(
        db, owner_id=effective_owner, limit=limit
    )
    return {
        "items": [
            {
                "id": r.id,
                "opportunity_id": r.opportunity_id,
                "suggested_stage": r.suggested_stage,
                "suggested_close_date": r.suggested_close_date.isoformat() if r.suggested_close_date else None,
                "suggested_amount": r.suggested_amount,
                "suggestion_source": r.suggestion_source,
                "evidence": json.loads(r.evidence_json) if r.evidence_json else None,
                "suggested_at": r.suggested_at.isoformat() if r.suggested_at else None,
            }
            for r in rows
        ],
        "total": len(rows),
    }


class ReviewDecisionPayload(BaseModel):
    decision: str = Field(..., pattern=r"^(applied|dismissed)$")


@router.post("/board/review-queue/{entry_id}/decide", response_model=ReviewDecideResponse)
async def board_review_decide(
    entry_id: int,
    payload: ReviewDecisionPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    entry = await db.get(PipelineReviewQueueEntry, entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Queue entry bulunamadı")

    # R4-TEN-20: cross-tenant guard — managers from tenant A must not be
    # able to decide queue entries for tenant B's opportunities. We always
    # load the parent Opportunity and assert same-tenant before either the
    # SALES_REP owner check or the manager bypass path takes effect.
    from app.core.exceptions import NotFoundException

    opp = await db.get(Opportunity, entry.opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Queue entry bulunamadı")
    try:
        assert_same_tenant(opp, current_user, exception_cls=NotFoundException)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Queue entry bulunamadı")

    # RBAC: rep can decide only on own opportunities
    if current_user.role == UserRole.SALES_REP.value:
        if opp.owner_id is None or int(opp.owner_id) != int(current_user.id):
            raise HTTPException(status_code=403, detail="Yetkisiz")
    updated = await pipeline_review_service.decide(
        db,
        entry_id=entry_id,
        decision=payload.decision,
        decided_by=current_user.id,
    )
    await db.commit()
    return {
        "id": updated.id,
        "decision": updated.decision,
        "decided_at": updated.decided_at.isoformat() if updated.decided_at else None,
    }


# ─────────────────────── Sprint N: NL semantic search ────────────────


class SemanticSearchPayload(BaseModel):
    query: str = Field(..., min_length=1, max_length=400)
    scopes: list[str] | None = None
    limit_per_scope: int = Field(10, ge=1, le=50)


@router.post("/search/semantic", response_model=SemanticSearchResponse)
async def search_semantic(
    payload: SemanticSearchPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_nl_search),
):
    items = await nl_search_service.semantic_search(
        db,
        query=payload.query,
        scopes=payload.scopes,
        limit_per_scope=payload.limit_per_scope,
    )
    return {"query": payload.query, "items": items, "total": len(items)}


# ─────────────────────── Sprint O: quote revisions ───────────────────


@router.get("/opportunities/{opportunity_id}/quote-revisions", response_model=QuoteRevisionsResponse)
async def list_quote_revisions(
    opportunity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    opp = await db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Fırsat bulunamadı")

    # V12 cross-tenant guard before owner check. Cross-tenant access
    # surfaces as 404 indistinguishable from "not found" so the API
    # doesn't leak which IDs exist in other tenants.
    from app.core.exceptions import NotFoundException

    try:
        assert_same_tenant(opp, current_user, exception_cls=NotFoundException)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Fırsat bulunamadı")

    if (
        current_user.role == UserRole.SALES_REP.value
        and opp.owner_id is not None
        and int(opp.owner_id) != int(current_user.id)
    ):
        raise HTTPException(status_code=403, detail="Yetkisiz")
    return {
        "opportunity_id": opportunity_id,
        "trees": await quote_revision_service.list_tree(
            db, opportunity_id=opportunity_id
        ),
    }


@router.post("/quotes/{quote_id}/revise", response_model=ReviseQuoteResponse)
async def revise_quote(
    quote_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    # V12 — load + tenant-check before delegating to the revision
    # service so cross-tenant probes can't trigger the revision side
    # effects (new quote row, item clones, FK updates).
    from app.core.exceptions import NotFoundException
    from app.models.quote import Quote

    quote = await db.get(Quote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="Quote bulunamadı")
    try:
        assert_same_tenant(quote, current_user, exception_cls=NotFoundException)
    except NotFoundException:
        raise HTTPException(status_code=404, detail="Quote bulunamadı")

    new_quote = await quote_revision_service.create_revision(
        db, quote_id=quote_id, created_by=current_user.id
    )
    if new_quote is None:
        raise HTTPException(status_code=404, detail="Quote bulunamadı")
    await db.commit()
    return {
        "id": new_quote.id,
        "quote_number": new_quote.quote_number,
        "revision_no": new_quote.revision_no,
        "parent_quote_id": new_quote.parent_quote_id,
    }


# ─────────────────────── Sprint P: slippage ──────────────────────────


@router.get("/slippage", response_model=SlippageEnvelope)
async def slippage_envelope(
    owner_id: int | None = Query(None),
    stage: str | None = Query(None),
    window_days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    # Reps default-scoped to their own pipeline.
    effective_owner = owner_id
    if current_user.role == UserRole.SALES_REP.value:
        effective_owner = current_user.id
    return await slippage_service.slippage_summary(
        db,
        owner_id=effective_owner,
        stage=stage,
        window_days=window_days,
    )


@router.get("/slippage/by-owner", response_model=SlippageByOwnerResponse)
async def slippage_per_owner(
    window_days: int = Query(30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_v2_board),
):
    _manager_only(current_user)
    return {"items": await slippage_service.slippage_by_owner(db, window_days=window_days)}
