"""D-019 — admin endpoints for the background-job DLQ.

    GET    /admin/dlq                    list unresolved failures
    POST   /admin/dlq/{id}/resolve       mark resolved (with note)
    POST   /admin/dlq/{id}/retry         increment retry counter

Operations role required (DLQ entries can contain sensitive job
payloads — KVKK export request IDs, sign-OTP token hashes, etc.).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.dlq_service import (
    list_unresolved,
    mark_resolved,
    mark_retry_attempted,
)


router = APIRouter(prefix="/admin/dlq", tags=["DLQ"])


def _require_ops(user: User) -> None:
    role = getattr(user, "role", None)
    if role not in {
        "operations", "ops_users", "ops_data", "ops_billing", "ops_audit",
    }:
        raise HTTPException(403, detail="dlq_requires_ops")


class ResolveRequest(BaseModel):
    note: Optional[str] = None


    # Round-15 N15-API-1: response_model exempt — admin/operational dict response
@router.get("")
async def list_dlq(
    limit: int = 200,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return unresolved DLQ entries. Tenant-agnostic (DLQ is platform-level)."""
    _require_ops(current_user)
    entries = await list_unresolved(db, limit=max(1, min(int(limit), 500)))
    return {
        "items": [
            {
                "id": e.id,
                "job_name": e.job_name,
                "error": e.error,
                "failed_at": e.failed_at,
                "retry_count": e.retry_count,
                "payload": e.payload,
            }
            for e in entries
        ],
        "total": len(entries),
    }


    # Round-15 N15-API-1: response_model exempt — admin/operational dict response
@router.post("/{dlq_id}/resolve")
async def resolve_dlq(
    dlq_id: int,
    payload: ResolveRequest = ResolveRequest(),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    _require_ops(current_user)
    await mark_resolved(
        db, dlq_id=dlq_id, user_id=current_user.id, note=payload.note
    )
    await db.commit()
    return {"resolved": True, "id": dlq_id}


    # Round-15 N15-API-1: response_model exempt — admin/operational dict response
@router.post("/{dlq_id}/retry")
async def retry_dlq(
    dlq_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Increment the retry counter. The actual re-execution is the
    operator's job (they fix the underlying issue then trigger the
    original endpoint again). This endpoint just records the attempt.
    """
    _require_ops(current_user)
    await mark_retry_attempted(db, dlq_id=dlq_id)
    await db.commit()
    return {"retry_recorded": True, "id": dlq_id}
