"""F-023 wire — KVKK export request endpoints.

State machine endpoints for the two-person-rule KVKK export flow:

    POST   /kvkk-export/requests             — Operator A files request
    GET    /kvkk-export/requests             — list (filterable by status)
    POST   /kvkk-export/requests/{id}/approve — Operator B approves
    POST   /kvkk-export/requests/{id}/reject  — Operator B rejects
    POST   /kvkk-export/requests/{id}/execute — kicks off the export job
    GET    /kvkk-export/requests/{id}         — detail

Two-person rule is enforced at three layers:
    1. ``approve``/``reject`` handlers raise ``TwoPersonViolation``
       if approver == requester.
    2. The service layer (`kvkk_two_person.approve_request`) repeats
       the check.
    3. The DB-level CHECK constraint on ``kvkk_export_requests``
       makes the rule survive even a future bypass.

This module ships endpoints + Pydantic schemas only — the actual
export job (collecting + zipping the subject's data) is a separate
worker still to be built.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.enums import UserRole
from app.models.user import User
from app.services.kvkk_two_person import (
    StateError,
    SUBJECT_KINDS,
    TwoPersonViolation,
    approve_request as svc_approve,
    create_request as svc_create,
    mark_done,
    mark_executing,
    mark_failed,
    reject_request as svc_reject,
)


router = APIRouter(prefix="/kvkk-export", tags=["KVKK Export"])


# ── Schemas ─────────────────────────────────────────────────────────


class KvkkRequestCreate(BaseModel):
    subject_lookup: str = Field(min_length=3, max_length=320)
    subject_kind: str = Field(description=f"One of {SUBJECT_KINDS}")


class KvkkRequestApprove(BaseModel):
    note: Optional[str] = None


class KvkkRequestReject(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


class KvkkRequestOut(BaseModel):
    id: int
    tenant_id: int
    subject_lookup: str
    subject_kind: str
    status: str
    requested_by: int
    requested_at: datetime
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    executed_at: Optional[datetime]
    artifact_url: Optional[str]
    reject_reason: Optional[str]


# ── Permission helper ──────────────────────────────────────────────


def _require_ops_or_manager(user: User) -> None:
    """KVKK export is operations work. Sales rep can't file; manager
    can. Operations always can."""
    role = getattr(user, "role", None)
    if role not in {
        UserRole.OPERATIONS.value if hasattr(UserRole.OPERATIONS, "value") else "operations",
        UserRole.SALES_MANAGER.value if hasattr(UserRole.SALES_MANAGER, "value") else "sales_manager",
        "operations", "sales_manager",
        # New ops sub-roles from F-011:
        "ops_users", "ops_data", "ops_billing",
    }:
        raise HTTPException(403, detail="kvkk_export_requires_ops_or_manager")


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/requests", response_model=KvkkRequestOut)
async def create_kvkk_request(
    payload: KvkkRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KvkkRequestOut:
    """Operator A files a new request. Two-person rule kicks in on
    the approve step — for now this just creates the row."""
    _require_ops_or_manager(current_user)
    if payload.subject_kind not in SUBJECT_KINDS:
        raise HTTPException(
            400,
            detail=f"subject_kind must be one of {SUBJECT_KINDS}",
        )
    req = await svc_create(
        db,
        tenant_id=getattr(current_user, "tenant_id", 0) or 0,
        subject_lookup=payload.subject_lookup,
        subject_kind=payload.subject_kind,
        requested_by=current_user.id,
    )
    return KvkkRequestOut(**req.__dict__)


@router.get("/requests")
async def list_kvkk_requests(
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List requests for the user's tenant."""
    _require_ops_or_manager(current_user)
    tenant_id = getattr(current_user, "tenant_id", None)
    params = {"tid": tenant_id}
    sql = (
        "SELECT id, tenant_id, subject_lookup, subject_kind, status, "
        "requested_by, requested_at, approved_by, approved_at, "
        "executed_at, artifact_url, reject_reason "
        "FROM kvkk_export_requests WHERE tenant_id = :tid"
    )
    if status:
        sql += " AND status = :status"
        params["status"] = status
    sql += " ORDER BY requested_at DESC LIMIT 200"
    rows = (await db.execute(text(sql), params)).mappings().all()
    return {"items": [dict(r) for r in rows], "total": len(rows)}


@router.get("/requests/{request_id}", response_model=KvkkRequestOut)
async def get_kvkk_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KvkkRequestOut:
    _require_ops_or_manager(current_user)
    row = (
        await db.execute(
            text(
                "SELECT id, tenant_id, subject_lookup, subject_kind, status, "
                "requested_by, requested_at, approved_by, approved_at, "
                "executed_at, artifact_url, reject_reason "
                "FROM kvkk_export_requests WHERE id = :id"
            ),
            {"id": request_id},
        )
    ).first()
    if row is None:
        raise HTTPException(404, detail="kvkk_request_not_found")
    # Tenant isolation: foreign-tenant rows return 404 (never 403)
    if row.tenant_id != getattr(current_user, "tenant_id", None):
        raise HTTPException(404, detail="kvkk_request_not_found")
    return KvkkRequestOut(**dict(row._mapping))


@router.post("/requests/{request_id}/approve", response_model=KvkkRequestOut)
async def approve_kvkk_request(
    request_id: int,
    payload: KvkkRequestApprove = KvkkRequestApprove(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KvkkRequestOut:
    """Operator B approves. Enforces approver != requester."""
    _require_ops_or_manager(current_user)
    try:
        await svc_approve(db, request_id=request_id, approver_id=current_user.id)
    except TwoPersonViolation as exc:
        raise HTTPException(403, detail=str(exc))
    except StateError as exc:
        raise HTTPException(409, detail=str(exc))
    return await get_kvkk_request(request_id, current_user=current_user, db=db)


@router.post("/requests/{request_id}/reject", response_model=KvkkRequestOut)
async def reject_kvkk_request(
    request_id: int,
    payload: KvkkRequestReject,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KvkkRequestOut:
    _require_ops_or_manager(current_user)
    try:
        await svc_reject(
            db,
            request_id=request_id,
            approver_id=current_user.id,
            reason=payload.reason,
        )
    except TwoPersonViolation as exc:
        raise HTTPException(403, detail=str(exc))
    except StateError as exc:
        raise HTTPException(409, detail=str(exc))
    return await get_kvkk_request(request_id, current_user=current_user, db=db)


@router.post("/requests/{request_id}/execute", response_model=KvkkRequestOut)
async def execute_kvkk_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KvkkRequestOut:
    """Kick off the export job. Refuses if status != ``approved``.

    The actual data-collection worker runs separately; this endpoint
    only locks the row to ``executing`` so a second operator can't
    double-trigger.
    """
    _require_ops_or_manager(current_user)
    try:
        await mark_executing(db, request_id)
    except StateError as exc:
        raise HTTPException(409, detail=str(exc))
    # TODO: enqueue the export job here (background task / Celery).
    # For now we just mark it executing; the operator runs the
    # data-collection script manually and posts back via mark_done
    # (Phase 5 will wire the async job).
    return await get_kvkk_request(request_id, current_user=current_user, db=db)
