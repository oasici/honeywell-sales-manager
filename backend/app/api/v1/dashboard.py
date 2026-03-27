from fastapi import APIRouter, Depends
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.spare_part import SparePart
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats")
async def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard KPIs for any authenticated user."""

    # Total emails
    total_emails_q = await db.execute(select(func.count(EmailRequest.id)))
    total_emails = total_emails_q.scalar() or 0

    # Parsed emails
    parsed_emails_q = await db.execute(
        select(func.count(EmailRequest.id)).where(EmailRequest.status != "new")
    )
    parsed_emails = parsed_emails_q.scalar() or 0

    # Total quotes
    total_quotes_q = await db.execute(select(func.count(Quote.id)))
    total_quotes = total_quotes_q.scalar() or 0

    # Sent quotes
    sent_quotes_q = await db.execute(
        select(func.count(Quote.id)).where(Quote.status == "sent")
    )
    sent_quotes = sent_quotes_q.scalar() or 0

    # Total spare parts
    total_parts_q = await db.execute(
        select(func.count(SparePart.id)).where(SparePart.is_active.is_(True))
    )
    total_parts = total_parts_q.scalar() or 0

    # Total customers
    total_customers_q = await db.execute(select(func.count(Customer.id)))
    total_customers = total_customers_q.scalar() or 0

    # Conversion rate: quotes with status in (sent, accepted) / total quotes
    converted_q = await db.execute(
        select(func.count(Quote.id)).where(Quote.status.in_(["sent", "accepted"]))
    )
    converted = converted_q.scalar() or 0
    conversion_rate = round((converted / total_quotes * 100) if total_quotes > 0 else 0.0, 2)

    # Average response hours: avg time from email received to quote created
    # Placeholder - this would require a join and datetime math
    avg_response_hours = 0.0

    # Pending review count
    pending_review_q = await db.execute(
        select(func.count(EmailRequest.id)).where(
            EmailRequest.review_status == "pending_review"
        )
    )
    pending_review_count = pending_review_q.scalar() or 0

    # Pending value: sum of grand_total for draft/pending_approval quotes
    pending_value_q = await db.execute(
        select(func.coalesce(func.sum(Quote.grand_total), 0.0)).where(
            Quote.status.in_(["draft", "pending_approval"])
        )
    )
    pending_value = pending_value_q.scalar() or 0.0

    # --- Ratio metrics for doughnut charts ---

    # 1) Answered emails (status=sent or quoted) vs total
    answered_emails_q = await db.execute(
        select(func.count(EmailRequest.id)).where(
            EmailRequest.status.in_(["quoted", "sent"])
        )
    )
    answered_emails = answered_emails_q.scalar() or 0

    # 2) Total requested parts value (from all parsed emails → quote items)
    total_parts_value_q = await db.execute(
        select(func.coalesce(func.sum(QuoteItem.line_total), 0.0))
    )
    total_parts_value = total_parts_value_q.scalar() or 0.0

    # Answered parts value (only from sent/accepted quotes)
    answered_parts_value_q = await db.execute(
        select(func.coalesce(func.sum(QuoteItem.line_total), 0.0))
        .join(Quote, QuoteItem.quote_id == Quote.id)
        .where(Quote.status.in_(["sent", "accepted"]))
    )
    answered_parts_value = answered_parts_value_q.scalar() or 0.0

    # 3) Total requested parts count
    total_parts_count_q = await db.execute(
        select(func.coalesce(func.sum(QuoteItem.quantity), 0))
    )
    total_parts_count = total_parts_count_q.scalar() or 0

    # Answered parts count (only from sent/accepted quotes)
    answered_parts_count_q = await db.execute(
        select(func.coalesce(func.sum(QuoteItem.quantity), 0))
        .join(Quote, QuoteItem.quote_id == Quote.id)
        .where(Quote.status.in_(["sent", "accepted"]))
    )
    answered_parts_count = answered_parts_count_q.scalar() or 0

    # 4) Approved/sent quotes vs total
    approved_quotes_q = await db.execute(
        select(func.count(Quote.id)).where(
            Quote.status.in_(["approved", "sent", "accepted"])
        )
    )
    approved_quotes = approved_quotes_q.scalar() or 0

    return {
        "total_emails": total_emails,
        "parsed_emails": parsed_emails,
        "total_quotes": total_quotes,
        "sent_quotes": sent_quotes,
        "total_parts": total_parts,
        "total_customers": total_customers,
        "conversion_rate": conversion_rate,
        "avg_response_hours": avg_response_hours,
        "pending_review_count": pending_review_count,
        "pending_value": round(pending_value, 2),
        # Doughnut chart ratios
        "answered_emails": answered_emails,
        "total_parts_value": round(total_parts_value, 2),
        "answered_parts_value": round(answered_parts_value, 2),
        "total_parts_count": total_parts_count,
        "answered_parts_count": answered_parts_count,
        "approved_quotes": approved_quotes,
    }
