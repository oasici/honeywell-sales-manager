from fastapi import APIRouter, Depends
from sqlalchemy import func, select
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
    """Dashboard KPIs for the current user's tenant.

    N15-AUTH-3 (Round-15) — every aggregate is scoped to ``current_user.tenant_id``.
    ``SparePart`` has no ``tenant_id`` column by design (catalog is Honeywell-wide,
    not per-tenant), so ``total_parts`` remains a global catalog count.
    """

    tenant_id = current_user.tenant_id

    # Total emails (tenant-scoped)
    total_emails_q = await db.execute(
        select(func.count(EmailRequest.id)).where(EmailRequest.tenant_id == tenant_id)
    )
    total_emails = total_emails_q.scalar() or 0

    # Parsed emails (tenant-scoped)
    parsed_emails_q = await db.execute(
        select(func.count(EmailRequest.id)).where(
            EmailRequest.tenant_id == tenant_id,
            EmailRequest.status != "new",
        )
    )
    parsed_emails = parsed_emails_q.scalar() or 0

    # Total quotes (tenant-scoped)
    total_quotes_q = await db.execute(
        select(func.count(Quote.id)).where(Quote.tenant_id == tenant_id)
    )
    total_quotes = total_quotes_q.scalar() or 0

    # Sent quotes (tenant-scoped)
    sent_quotes_q = await db.execute(
        select(func.count(Quote.id)).where(
            Quote.tenant_id == tenant_id,
            Quote.status == "sent",
        )
    )
    sent_quotes = sent_quotes_q.scalar() or 0

    # Total spare parts — catalog is shared across tenants by design;
    # this stays global. See SparePart model (no tenant_id column).
    total_parts_q = await db.execute(
        select(func.count(SparePart.id)).where(SparePart.is_active.is_(True))
    )
    total_parts = total_parts_q.scalar() or 0

    # Total customers (tenant-scoped)
    total_customers_q = await db.execute(
        select(func.count(Customer.id)).where(Customer.tenant_id == tenant_id)
    )
    total_customers = total_customers_q.scalar() or 0

    # Conversion rate: quotes with status in (sent, accepted) / total quotes (tenant-scoped)
    converted_q = await db.execute(
        select(func.count(Quote.id)).where(
            Quote.tenant_id == tenant_id,
            Quote.status.in_(["sent", "accepted"]),
        )
    )
    converted = converted_q.scalar() or 0
    conversion_rate = round((converted / total_quotes * 100) if total_quotes > 0 else 0.0, 2)

    # Average response hours: avg time from email received to quote created
    # Placeholder - this would require a join and datetime math
    avg_response_hours = 0.0

    # Pending review count (tenant-scoped)
    pending_review_q = await db.execute(
        select(func.count(EmailRequest.id)).where(
            EmailRequest.tenant_id == tenant_id,
            EmailRequest.review_status == "pending_review",
        )
    )
    pending_review_count = pending_review_q.scalar() or 0

    # Pending value: sum of grand_total for draft/pending_approval quotes (tenant-scoped)
    pending_value_q = await db.execute(
        select(func.coalesce(func.sum(Quote.grand_total), 0.0)).where(
            Quote.tenant_id == tenant_id,
            Quote.status.in_(["draft", "pending_approval"]),
        )
    )
    pending_value = pending_value_q.scalar() or 0.0

    # --- Ratio metrics for doughnut charts ---

    # 1) Answered emails (status=sent or quoted) vs total — tenant-scoped
    answered_emails_q = await db.execute(
        select(func.count(EmailRequest.id)).where(
            EmailRequest.tenant_id == tenant_id,
            EmailRequest.status.in_(["quoted", "sent"]),
        )
    )
    answered_emails = answered_emails_q.scalar() or 0

    # 2) Total requested parts value (from all parsed emails → quote items)
    # Joined through Quote for tenant scope — ``QuoteItem.tenant_id`` is
    # nullable for in-flight cohort 9 promotion, so the parent join is the
    # canonical filter today.
    total_parts_value_q = await db.execute(
        select(func.coalesce(func.sum(QuoteItem.line_total), 0.0))
        .join(Quote, QuoteItem.quote_id == Quote.id)
        .where(Quote.tenant_id == tenant_id)
    )
    total_parts_value = total_parts_value_q.scalar() or 0.0

    # Answered parts value (only from sent/accepted quotes) — tenant-scoped via Quote
    answered_parts_value_q = await db.execute(
        select(func.coalesce(func.sum(QuoteItem.line_total), 0.0))
        .join(Quote, QuoteItem.quote_id == Quote.id)
        .where(
            Quote.tenant_id == tenant_id,
            Quote.status.in_(["sent", "accepted"]),
        )
    )
    answered_parts_value = answered_parts_value_q.scalar() or 0.0

    # 3) Total requested parts count — tenant-scoped via Quote join
    total_parts_count_q = await db.execute(
        select(func.coalesce(func.sum(QuoteItem.quantity), 0))
        .join(Quote, QuoteItem.quote_id == Quote.id)
        .where(Quote.tenant_id == tenant_id)
    )
    total_parts_count = total_parts_count_q.scalar() or 0

    # Answered parts count (only from sent/accepted quotes) — tenant-scoped
    answered_parts_count_q = await db.execute(
        select(func.coalesce(func.sum(QuoteItem.quantity), 0))
        .join(Quote, QuoteItem.quote_id == Quote.id)
        .where(
            Quote.tenant_id == tenant_id,
            Quote.status.in_(["sent", "accepted"]),
        )
    )
    answered_parts_count = answered_parts_count_q.scalar() or 0

    # 4) Approved/sent quotes vs total — tenant-scoped
    approved_quotes_q = await db.execute(
        select(func.count(Quote.id)).where(
            Quote.tenant_id == tenant_id,
            Quote.status.in_(["approved", "sent", "accepted"]),
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
