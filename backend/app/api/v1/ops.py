"""Feature-8: Operational queues for RevOps."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.email_request import EmailRequest
from app.models.enums import UserRole
from app.models.quote import Quote
from app.models.user import User

router = APIRouter(prefix="/ops", tags=["Operations"])


@router.get("/queues")
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
