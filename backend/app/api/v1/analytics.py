from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, and_, extract, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import require_role
from app.models.enums import UserRole
from app.models.price_entry import PriceEntry
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.spare_part import SparePart
from app.models.user import User

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/top-parts")
async def get_top_parts(
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    limit: int = Query(10, ge=1, le=100, description="Number of results"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Top requested parts by quote item count within the lookback period."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(
            QuoteItem.honeywell_code,
            func.count(QuoteItem.id).label("request_count"),
            func.sum(QuoteItem.quantity).label("total_quantity"),
            func.sum(QuoteItem.line_total).label("total_value"),
        )
        .join(Quote, QuoteItem.quote_id == Quote.id)
        .where(Quote.created_at >= cutoff)
        .where(QuoteItem.honeywell_code.isnot(None))
        .group_by(QuoteItem.honeywell_code)
        .order_by(func.count(QuoteItem.id).desc())
        .limit(limit)
    )
    rows = result.all()

    items = []
    for row in rows:
        # Look up part name
        part_result = await db.execute(
            select(SparePart.name_en, SparePart.name_tr, SparePart.category).where(
                SparePart.honeywell_code == row.honeywell_code
            )
        )
        part_info = part_result.first()

        items.append({
            "honeywell_code": row.honeywell_code,
            "request_count": row.request_count,
            "total_quantity": row.total_quantity or 0,
            "total_value": round(row.total_value or 0, 2),
            "name_en": part_info.name_en if part_info else None,
            "name_tr": part_info.name_tr if part_info else None,
            "category": part_info.category if part_info else None,
        })

    return items


@router.get("/monthly-trend")
async def get_monthly_trend(
    months: int = Query(12, ge=1, le=36, description="Number of months to look back"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Monthly quote count and revenue trend."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)

    result = await db.execute(
        select(
            extract("year", Quote.created_at).label("year"),
            extract("month", Quote.created_at).label("month"),
            func.count(Quote.id).label("quote_count"),
            func.coalesce(func.sum(Quote.grand_total), 0.0).label("revenue"),
            func.count(
                case((Quote.status == "sent", Quote.id))
            ).label("sent_count"),
        )
        .where(Quote.created_at >= cutoff)
        .group_by(
            extract("year", Quote.created_at),
            extract("month", Quote.created_at),
        )
        .order_by(
            extract("year", Quote.created_at),
            extract("month", Quote.created_at),
        )
    )
    rows = result.all()

    items = [
        {
            "year": int(row.year),
            "month": int(row.month),
            "quote_count": row.quote_count,
            "revenue": round(row.revenue, 2),
            "sent_count": row.sent_count,
        }
        for row in rows
    ]

    return items


@router.get("/category-breakdown")
async def get_category_breakdown(
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Category distribution of quoted items within the lookback period."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(
            SparePart.category,
            func.count(QuoteItem.id).label("item_count"),
            func.sum(QuoteItem.quantity).label("total_quantity"),
            func.coalesce(func.sum(QuoteItem.line_total), 0.0).label("total_value"),
        )
        .join(SparePart, QuoteItem.spare_part_id == SparePart.id)
        .join(Quote, QuoteItem.quote_id == Quote.id)
        .where(Quote.created_at >= cutoff)
        .group_by(SparePart.category)
        .order_by(func.sum(QuoteItem.line_total).desc())
    )
    rows = result.all()

    items = [
        {
            "category": row.category or "Uncategorized",
            "item_count": row.item_count,
            "total_quantity": row.total_quantity or 0,
            "total_value": round(row.total_value, 2),
        }
        for row in rows
    ]

    return items


@router.get("/parts-without-price")
async def get_parts_without_price(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Parts requested in quotes that have no pricing (supplier_price AND transfer_price both null)."""
    from sqlalchemy import or_

    # Get all honeywell codes from quote items
    quoted_codes_q = await db.execute(
        select(QuoteItem.honeywell_code)
        .where(QuoteItem.honeywell_code.isnot(None))
        .where(QuoteItem.honeywell_code != "-")
        .where(QuoteItem.honeywell_code != "")
        .distinct()
    )
    quoted_codes = {row[0] for row in quoted_codes_q.all()}

    if not quoted_codes:
        return []

    # Find parts that exist but have NO price (supplier_price AND transfer_price both null)
    result = await db.execute(
        select(SparePart)
        .where(SparePart.honeywell_code.in_(quoted_codes))
        .where(SparePart.is_active.is_(True))
        .where(SparePart.supplier_price.is_(None))
        .where(SparePart.transfer_price.is_(None))
        .order_by(SparePart.honeywell_code)
    )
    parts = result.scalars().all()

    # Also find codes that were quoted but don't exist in catalog at all
    existing_codes_q = await db.execute(
        select(SparePart.honeywell_code)
        .where(SparePart.honeywell_code.in_(quoted_codes))
    )
    existing_codes = {row[0] for row in existing_codes_q.all()}
    unknown_codes = sorted(quoted_codes - existing_codes)

    items = [
        {
            "id": p.id,
            "honeywell_code": p.honeywell_code,
            "name_en": p.name_en,
            "name_tr": p.name_tr,
            "category": p.category,
            "status": "no_price",
        }
        for p in parts
    ]

    for code in unknown_codes:
        items.append({
            "id": None,
            "honeywell_code": code,
            "name_en": None,
            "name_tr": None,
            "category": None,
            "status": "unknown_part",
        })

    return items


@router.get("/ai-usage")
async def get_ai_usage(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """AI usage statistics: parse counts, correction rates, model performance."""
    from app.models.email_request import EmailRequest
    from app.models.ai_training_data import AITrainingData

    total_parsed = (await db.execute(
        select(func.count(EmailRequest.id)).where(EmailRequest.status != "new")
    )).scalar() or 0

    approved = (await db.execute(
        select(func.count(EmailRequest.id)).where(EmailRequest.review_status == "approved")
    )).scalar() or 0
    pending = (await db.execute(
        select(func.count(EmailRequest.id)).where(EmailRequest.review_status == "pending_review")
    )).scalar() or 0
    rejected = (await db.execute(
        select(func.count(EmailRequest.id)).where(EmailRequest.review_status == "rejected")
    )).scalar() or 0

    avg_confidence = (await db.execute(
        select(func.avg(EmailRequest.category_confidence)).where(
            EmailRequest.category_confidence.isnot(None)
        )
    )).scalar() or 0.0

    total_corrections = (await db.execute(
        select(func.count(AITrainingData.id))
    )).scalar() or 0

    correction_fields_raw = (await db.execute(
        select(AITrainingData.correction_fields)
    )).scalars().all()

    field_counts: dict[str, int] = {}
    for fields_str in correction_fields_raw:
        if fields_str:
            for f in fields_str.split(","):
                f = f.strip()
                if f:
                    field_counts[f] = field_counts.get(f, 0) + 1

    correction_rate = round(total_corrections / total_parsed * 100, 1) if total_parsed > 0 else 0.0

    return {
        "total_parsed": total_parsed,
        "review_breakdown": {"approved": approved, "pending_review": pending, "rejected": rejected},
        "average_confidence": round(avg_confidence, 3),
        "total_corrections": total_corrections,
        "correction_rate_pct": correction_rate,
        "most_corrected_fields": dict(sorted(field_counts.items(), key=lambda x: -x[1])[:5]),
        "estimated_api_cost_usd": round(total_parsed * 0.003, 2),
    }
