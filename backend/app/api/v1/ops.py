"""Feature-8: Operational queues for RevOps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.email_request import EmailRequest
from app.models.enums import UserRole
from app.models.feature_usage import FeatureUsage
from app.models.quote import Quote
from app.models.user import User

router = APIRouter(prefix="/ops", tags=["Operations"])


@router.get("/queues", response_model=dict)
async def get_queues(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Operational queues: review pending, approval pending, expiring soon."""
    now = datetime.now(timezone.utc)

    # Review pending emails
    review_q = await db.execute(
        select(EmailRequest.id, EmailRequest.from_address, EmailRequest.subject, EmailRequest.created_at)
        .where(EmailRequest.review_status == "pending_review")
        .order_by(EmailRequest.created_at.asc())
        .limit(50)
    )
    review_pending = [
        {"id": r.id, "from_address": r.from_address, "subject": r.subject, "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in review_q.all()
    ]

    # Quote approval pending
    approval_q = await db.execute(
        select(Quote.id, Quote.quote_number, Quote.grand_total, Quote.created_at)
        .where(Quote.status == "pending_approval")
        .order_by(Quote.created_at.asc())
        .limit(50)
    )
    approval_pending = [
        {"id": r.id, "quote_number": r.quote_number, "grand_total": round(r.grand_total, 2), "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in approval_q.all()
    ]

    # Expiring soon (within 7 days)
    expiring_q = await db.execute(
        select(Quote)
        .where(
            Quote.status.in_(["draft", "approved", "sent"]),
            Quote.valid_days.isnot(None),
        )
        .order_by(Quote.created_at.asc())
        .limit(100)
    )
    expiring = []
    for q in expiring_q.scalars().all():
        if q.created_at and q.valid_days:
            expiry = q.created_at + timedelta(days=q.valid_days)
            remaining = (expiry - now).days
            if 0 <= remaining <= 7:
                expiring.append({
                    "id": q.id,
                    "quote_number": q.quote_number,
                    "grand_total": round(q.grand_total, 2),
                    "days_remaining": remaining,
                    "expiry_date": expiry.isoformat()[:10],
                })

    return {
        "review_pending": review_pending,
        "review_pending_count": len(review_pending),
        "quote_approval_pending": approval_pending,
        "approval_pending_count": len(approval_pending),
        "expiring_quotes": expiring,
        "expiring_count": len(expiring),
    }


@router.get("/feature-usage", response_model=dict)
async def get_feature_usage(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
    feature_name: str | None = None,
    days: int = 30,
):
    """Ozellik kullanim istatistikleri (toplam ve aksiyona gore)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Total usage per feature
    stmt = (
        select(
            FeatureUsage.feature_name,
            FeatureUsage.action,
            func.count().label("count"),
        )
        .where(FeatureUsage.created_at >= cutoff)
        .group_by(FeatureUsage.feature_name, FeatureUsage.action)
        .order_by(func.count().desc())
    )
    if feature_name:
        stmt = stmt.where(FeatureUsage.feature_name == feature_name)

    result = await db.execute(stmt)
    rows = result.all()

    usage_stats = {}
    for row in rows:
        name = row.feature_name
        if name not in usage_stats:
            usage_stats[name] = {"total": 0, "actions": {}}
        usage_stats[name]["total"] += row.count
        usage_stats[name]["actions"][row.action] = row.count

    return {
        "period_days": days,
        "features": usage_stats,
    }


@router.get("/feature-flags", response_model=dict)
async def get_feature_flags(
    current_user: User = Depends(get_current_user),
):
    """Return public feature-flag states (allowlisted).

    N15-OPS-1 (Round-15) — previously this endpoint returned every
    ``FEATURE_*`` attribute on the settings object, including
    experimental / internal flags that ``backend/app/api/v1/config.py``
    deliberately withholds via ``_PUBLIC_FEATURE_FLAGS``. Now both
    endpoints honor the same allowlist so the SPA never sees roadmap
    flags the company hasn't announced.
    """
    from app.api.v1.config import _PUBLIC_FEATURE_FLAGS

    flags: dict[str, bool] = {}
    for name in _PUBLIC_FEATURE_FLAGS:
        if hasattr(settings, name):
            flags[name] = bool(getattr(settings, name))
    return {"data": flags}


@router.get("/dashboard", response_model=dict)
async def get_ops_dashboard(
    current_user: User = Depends(get_current_user),
):
    """Return operational metrics."""
    from app.core.event_bus import event_bus
    from app.tasks.scheduler import get_task_stats

    enabled_count = sum(
        1
        for k, v in settings.__dict__.items()
        if k.startswith("FEATURE_") and v is True
    )

    return {
        "data": {
            "event_bus": event_bus.get_stats(),
            "scheduler": get_task_stats(),
            "feature_flags_enabled": enabled_count,
        },
    }
