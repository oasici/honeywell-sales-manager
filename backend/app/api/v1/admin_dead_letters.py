"""Dead-letter event admin endpoints (R4-EG-1).

List, inspect, and replay events that exhausted retries in
``event_bus.publish``. Manager-only; the admin sidebar exposes
this surface alongside the existing event audit log.
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.core.event_bus import event_bus
from app.models.dead_letter_event import DeadLetterEvent
from app.models.enums import UserRole
from app.models.user import User
from app.schemas.common import PaginatedResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/dead-letter-events", tags=["Admin"])


def _to_dict(row: DeadLetterEvent) -> dict:
    return {
        "id": row.id,
        "event_type": row.event_type,
        "handler_name": row.handler_name,
        "payload_json": row.payload_json,
        "error_message": row.error_message,
        "error_traceback": row.error_traceback,
        "attempt_count": row.attempt_count,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "replayed_at": row.replayed_at.isoformat() if row.replayed_at else None,
        "replayed_by": row.replayed_by,
    }


@router.get("/", response_model=PaginatedResponse[dict])
async def list_dead_letters(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(50, ge=1, le=100),
    event_type: str | None = Query(None),
    handler_name: str | None = Query(None),
    only_unreplayed: bool = Query(False, description="Hide rows already replayed"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """List dead-letter events with filters + pagination."""
    base = select(DeadLetterEvent).order_by(DeadLetterEvent.created_at.desc())
    count_q = select(func.count(DeadLetterEvent.id))
    if event_type:
        base = base.where(DeadLetterEvent.event_type == event_type)
        count_q = count_q.where(DeadLetterEvent.event_type == event_type)
    if handler_name:
        base = base.where(DeadLetterEvent.handler_name == handler_name)
        count_q = count_q.where(DeadLetterEvent.handler_name == handler_name)
    if only_unreplayed:
        base = base.where(DeadLetterEvent.replayed_at.is_(None))
        count_q = count_q.where(DeadLetterEvent.replayed_at.is_(None))

    total = (await db.execute(count_q)).scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(base.offset(offset).limit(page_size))
    rows = result.scalars().all()

    return {
        "items": [_to_dict(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.post("/{entry_id}/replay")
async def replay_dead_letter(
    entry_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Re-invoke the original handler with the stored payload.

    The replay goes through ``event_bus.publish`` so all subscribers
    of the event_type re-run, not just the originally-failing handler
    — this matches operator intent when an external dependency
    recovers (e.g. webhook URL came back online and we want all the
    queued events to fire). Mark the row as replayed regardless of
    whether the replay raised.
    """
    row = (
        await db.execute(
            select(DeadLetterEvent).where(DeadLetterEvent.id == entry_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")
    if row.replayed_at is not None:
        raise HTTPException(status_code=409, detail="Bu kayit zaten replay edildi")

    try:
        payload = json.loads(row.payload_json)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Payload JSON parse edilemedi; manuel inceleme gerekli",
        )

    try:
        await event_bus.publish(row.event_type, payload)
    except Exception as exc:
        logger.exception("dead-letter replay failed for %s", row.id)
        # Don't update the row — the operator should be able to retry.
        raise HTTPException(
            status_code=500,
            detail=f"Replay yine basarisiz oldu: {str(exc)[:200]}",
        )

    row.replayed_at = datetime.now(timezone.utc)
    row.replayed_by = current_user.id
    await db.commit()

    return {"status": "replayed", "id": row.id}


@router.delete("/{entry_id}", status_code=204)
async def delete_dead_letter(
    entry_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Permanently delete a dead-letter row (after manual triage)."""
    row = (
        await db.execute(
            select(DeadLetterEvent).where(DeadLetterEvent.id == entry_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")
    await db.delete(row)
    await db.commit()
    return None


@router.get("/stats")
async def dead_letter_stats(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Aggregate stats for the admin dashboard."""
    rows = (
        await db.execute(
            select(
                DeadLetterEvent.event_type,
                DeadLetterEvent.handler_name,
                func.count(DeadLetterEvent.id).label("total"),
                func.count(DeadLetterEvent.replayed_at).label("replayed"),
            ).group_by(DeadLetterEvent.event_type, DeadLetterEvent.handler_name)
        )
    ).all()
    return {
        "groups": [
            {
                "event_type": r.event_type,
                "handler_name": r.handler_name,
                "total": int(r.total),
                "replayed": int(r.replayed),
                "pending": int(r.total) - int(r.replayed),
            }
            for r in rows
        ]
    }
