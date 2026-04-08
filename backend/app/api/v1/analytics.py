from datetime import datetime, timedelta, timezone

import sqlalchemy
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, and_, extract, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.customer import Customer
from app.models.email_request import EmailRequest
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
    return await _compute_ai_metrics(db)


@router.get("/ai-quality")
async def get_ai_quality(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """AI quality analytics: success/failure ratio, fallback rate, correction trends.

    Reports only — does not change parser behavior.
    """
    base_metrics = await _compute_ai_metrics(db)

    from app.models.email_request import EmailRequest

    # Parse success vs failure
    total_emails = (await db.execute(
        select(func.count(EmailRequest.id))
    )).scalar() or 0
    parse_errors = (await db.execute(
        select(func.count(EmailRequest.id)).where(EmailRequest.status == "error")
    )).scalar() or 0
    parse_success = base_metrics["total_parsed"] - parse_errors
    success_rate = round(parse_success / total_emails * 100, 1) if total_emails > 0 else 0.0

    # Fallback rate (emails without Claude confidence — regex fallback assumed)
    no_confidence = (await db.execute(
        select(func.count(EmailRequest.id)).where(
            and_(
                EmailRequest.status != "new",
                EmailRequest.category_confidence.is_(None),
            )
        )
    )).scalar() or 0
    fallback_rate = round(no_confidence / base_metrics["total_parsed"] * 100, 1) if base_metrics["total_parsed"] > 0 else 0.0

    # Monthly correction trend (last 6 months)
    from app.models.ai_training_data import AITrainingData
    six_months_ago = datetime.now(timezone.utc) - timedelta(days=180)
    correction_trend_q = await db.execute(
        select(
            extract("year", AITrainingData.created_at).label("year"),
            extract("month", AITrainingData.created_at).label("month"),
            func.count(AITrainingData.id).label("correction_count"),
        )
        .where(AITrainingData.created_at >= six_months_ago)
        .group_by(
            extract("year", AITrainingData.created_at),
            extract("month", AITrainingData.created_at),
        )
        .order_by(
            extract("year", AITrainingData.created_at),
            extract("month", AITrainingData.created_at),
        )
    )
    correction_trend = [
        {"year": int(r.year), "month": int(r.month), "corrections": r.correction_count}
        for r in correction_trend_q.all()
    ]

    return {
        **base_metrics,
        "total_emails": total_emails,
        "parse_success": parse_success,
        "parse_errors": parse_errors,
        "success_rate_pct": success_rate,
        "fallback_rate_pct": fallback_rate,
        "correction_trend": correction_trend,
    }


async def _compute_ai_metrics(db: AsyncSession) -> dict:
    """Shared AI metrics computation for ai-usage and ai-quality endpoints."""
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


# ══════════════════════════════════════════════════════════════
# FAZ-3 ANALYTICS ENDPOINTS
# ══════════════════════════════════════════════════════════════


@router.get("/forecast")
async def get_forecast(
    window: int = Query(30, description="Forecast window: 7, 30, or 90 days"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Feature-1: Simple forecast + pipeline coverage."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window)

    # Open quotes (draft, approved, sent — not yet won/lost/expired)
    open_statuses = ["draft", "pending_approval", "approved", "sent"]
    open_total_q = await db.execute(
        select(func.coalesce(func.sum(Quote.grand_total), 0.0)).where(
            Quote.status.in_(open_statuses)
        )
    )
    open_quotes_total = round(float(open_total_q.scalar() or 0), 2)

    # Historical win rate for forecast heuristic
    total_in_window = (await db.execute(
        select(func.count(Quote.id)).where(Quote.created_at >= cutoff)
    )).scalar() or 0
    won_in_window = (await db.execute(
        select(func.count(Quote.id)).where(
            and_(Quote.created_at >= cutoff, Quote.status == "accepted")
        )
    )).scalar() or 0
    win_rate = won_in_window / total_in_window if total_in_window > 0 else 0.3

    forecast_total = round(open_quotes_total * win_rate, 2)

    # Daily breakdown for trend (cast to date for SQLite + PG compatibility)
    day_col = func.cast(Quote.created_at, sqlalchemy.Date).label("day")
    by_day_q = await db.execute(
        select(
            day_col,
            func.coalesce(func.sum(Quote.grand_total), 0.0).label("value"),
            func.count(Quote.id).label("count"),
        )
        .where(Quote.created_at >= cutoff)
        .group_by(day_col)
        .order_by(day_col)
    )
    by_day = [
        {"date": str(r.day) if r.day else None, "value": round(float(r.value), 2), "count": r.count}
        for r in by_day_q.all()
    ]

    return {
        "window_days": window,
        "open_quotes_total": open_quotes_total,
        "forecast_total": forecast_total,
        "win_rate": round(win_rate, 3),
        "coverage_ratio": round(open_quotes_total / forecast_total, 2) if forecast_total > 0 else 0,
        "by_day": by_day,
    }


@router.get("/slippage")
async def get_slippage(
    no_touch_days: int = Query(7, ge=1, le=90, description="No-touch threshold"),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Feature-2: Deal slippage & aging radar."""
    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=no_touch_days)

    # Risky quotes: open + not updated recently
    open_statuses = ["draft", "pending_approval", "approved", "sent"]
    risky_q = await db.execute(
        select(Quote)
        .where(Quote.status.in_(open_statuses), Quote.updated_at < threshold)
        .order_by(Quote.updated_at.asc())
        .limit(limit)
    )
    risky_quotes = risky_q.scalars().all()

    risky_list = []
    for q in risky_quotes:
        days_since = (now - q.updated_at).days if q.updated_at else 999
        risky_list.append({
            "id": q.id,
            "quote_number": q.quote_number,
            "customer_id": q.customer_id,
            "customer_name": q.customer.name if q.customer else None,
            "status": q.status,
            "grand_total": q.grand_total,
            "days_since_touch": days_since,
            "updated_at": q.updated_at.isoformat() if q.updated_at else None,
        })

    # Aging buckets
    all_open_q = await db.execute(
        select(Quote.updated_at).where(Quote.status.in_(open_statuses))
    )
    buckets = {"0-7": 0, "8-14": 0, "15-30": 0, "31-60": 0, "60+": 0}
    for row in all_open_q.all():
        if row.updated_at:
            age = (now - row.updated_at).days
            if age <= 7:
                buckets["0-7"] += 1
            elif age <= 14:
                buckets["8-14"] += 1
            elif age <= 30:
                buckets["15-30"] += 1
            elif age <= 60:
                buckets["31-60"] += 1
            else:
                buckets["60+"] += 1

    return {
        "no_touch_days": no_touch_days,
        "risky_quotes": risky_list,
        "aging_buckets": [{"bucket": k, "count": v} for k, v in buckets.items()],
    }


@router.get("/funnel")
async def get_funnel(
    window: int = Query(30, ge=1, le=365, description="Lookback days"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Feature-4: Stage conversion funnel (quote lifecycle)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    stages = ["draft", "pending_approval", "approved", "sent", "accepted", "rejected", "expired"]
    counts = {}
    for status in stages:
        q = await db.execute(
            select(func.count(Quote.id)).where(
                and_(Quote.created_at >= cutoff, Quote.status == status)
            )
        )
        counts[status] = q.scalar() or 0

    total = sum(counts.values())
    funnel = []
    for status in stages:
        funnel.append({
            "stage": status,
            "count": counts[status],
            "pct": round(counts[status] / total * 100, 1) if total > 0 else 0,
        })

    # Conversion rates between stages
    conversions = []
    ordered = ["draft", "sent", "approved", "accepted"]
    for i in range(len(ordered) - 1):
        from_count = counts.get(ordered[i], 0) + sum(counts.get(s, 0) for s in ordered[i + 1:])
        to_count = sum(counts.get(s, 0) for s in ordered[i + 1:])
        rate = round(to_count / from_count * 100, 1) if from_count > 0 else 0
        conversions.append({
            "from": ordered[i],
            "to": ordered[i + 1],
            "rate": rate,
        })

    return {"window_days": window, "funnel": funnel, "conversions": conversions}


@router.get("/rep-scorecards")
async def get_rep_scorecards(
    window: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Feature-5: Rep performance scorecards."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    reps_q = await db.execute(
        select(User).where(User.role.in_(["sales_rep", "sales_manager"]), User.is_active.is_(True))
    )
    reps = reps_q.scalars().all()

    scorecards = []
    for rep in reps:
        base = and_(Quote.created_by == rep.id, Quote.created_at >= cutoff)
        total = (await db.execute(select(func.count(Quote.id)).where(base))).scalar() or 0
        sent = (await db.execute(select(func.count(Quote.id)).where(base, Quote.status == "sent"))).scalar() or 0
        approved = (await db.execute(select(func.count(Quote.id)).where(base, Quote.status == "approved"))).scalar() or 0
        won = (await db.execute(select(func.count(Quote.id)).where(base, Quote.status == "accepted"))).scalar() or 0
        revenue = (await db.execute(select(func.coalesce(func.sum(Quote.grand_total), 0.0)).where(base))).scalar() or 0

        avg_discount = (await db.execute(
            select(func.avg(Quote.discount_total)).where(base, Quote.discount_total > 0)
        )).scalar() or 0

        win_rate = round(won / total * 100, 1) if total > 0 else 0

        scorecards.append({
            "user_id": rep.id,
            "full_name": rep.full_name,
            "role": rep.role,
            "quote_count": total,
            "sent_count": sent,
            "approved_count": approved,
            "won_count": won,
            "win_rate": win_rate,
            "revenue": round(float(revenue), 2),
            "avg_discount": round(float(avg_discount), 2),
        })

    scorecards.sort(key=lambda x: x["revenue"], reverse=True)
    return {"window_days": window, "scorecards": scorecards}


@router.get("/discounts")
async def get_discounts(
    window: int = Query(90, ge=1, le=365),
    threshold_pct: float = Query(25.0, description="Outlier threshold %"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Feature-6: Discount health + outlier alerts."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    # All quotes with discount in window
    q = await db.execute(
        select(Quote.id, Quote.quote_number, Quote.customer_id, Quote.subtotal,
               Quote.discount_total, Quote.grand_total, Quote.created_by)
        .where(Quote.created_at >= cutoff, Quote.subtotal > 0)
        .order_by(Quote.created_at.desc())
    )
    rows = q.all()

    discount_rates = []
    outliers = []
    for r in rows:
        rate = round((r.discount_total / r.subtotal) * 100, 1) if r.subtotal > 0 else 0
        discount_rates.append(rate)
        if rate >= threshold_pct:
            outliers.append({
                "id": r.id,
                "quote_number": r.quote_number,
                "discount_rate": rate,
                "discount_total": round(r.discount_total, 2),
                "grand_total": round(r.grand_total, 2),
            })

    discount_rates.sort()
    n = len(discount_rates)
    p50 = discount_rates[n // 2] if n > 0 else 0
    p90 = discount_rates[int(n * 0.9)] if n > 0 else 0

    return {
        "window_days": window,
        "total_quotes": n,
        "p50_discount_rate": p50,
        "p90_discount_rate": p90,
        "avg_discount_rate": round(sum(discount_rates) / n, 1) if n > 0 else 0,
        "outlier_count": len(outliers),
        "outliers": outliers[:50],
    }


@router.get("/sla")
async def get_sla(
    window: int = Query(30, ge=1, le=365),
    sla_minutes: int = Query(480, description="SLA target in minutes (default 8h)"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Feature-7: Speed-to-lead / response SLA dashboard."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    # First action time = earliest quote created_at for each email
    q = await db.execute(
        select(
            EmailRequest.id,
            EmailRequest.from_address,
            EmailRequest.subject,
            EmailRequest.created_at.label("email_at"),
            func.min(Quote.created_at).label("first_action_at"),
        )
        .outerjoin(Quote, Quote.email_request_id == EmailRequest.id)
        .where(EmailRequest.created_at >= cutoff)
        .group_by(EmailRequest.id, EmailRequest.from_address, EmailRequest.subject, EmailRequest.created_at)
    )
    rows = q.all()

    response_minutes = []
    breaches = []
    for r in rows:
        if r.first_action_at and r.email_at:
            delta = (r.first_action_at - r.email_at).total_seconds() / 60
            response_minutes.append(delta)
            if delta > sla_minutes:
                breaches.append({
                    "email_id": r.id,
                    "from_address": r.from_address,
                    "subject": r.subject[:80] if r.subject else "",
                    "response_minutes": round(delta),
                })

    response_minutes.sort()
    n = len(response_minutes)
    median = response_minutes[n // 2] if n > 0 else 0

    return {
        "window_days": window,
        "sla_target_minutes": sla_minutes,
        "total_emails": len(rows),
        "emails_with_action": n,
        "median_first_action_minutes": round(median),
        "breaches_count": len(breaches),
        "breaches": breaches[:30],
    }


@router.get("/win-loss-reasons")
async def get_win_loss_reasons(
    window: int = Query(90, ge=1, le=365),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Feature-3: Win/loss reason breakdown."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    q = await db.execute(
        select(
            Quote.close_reason,
            func.count(Quote.id).label("count"),
            func.coalesce(func.sum(Quote.grand_total), 0.0).label("total_value"),
        )
        .where(Quote.created_at >= cutoff, Quote.close_reason.isnot(None))
        .group_by(Quote.close_reason)
        .order_by(func.count(Quote.id).desc())
    )
    rows = q.all()

    return {
        "window_days": window,
        "reasons": [
            {"reason": r.close_reason, "count": r.count, "total_value": round(float(r.total_value), 2)}
            for r in rows
        ],
    }


@router.get("/data-quality")
async def get_data_quality(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Feature-9: Data quality & completeness panel."""
    # Customer completeness
    total_customers = (await db.execute(select(func.count(Customer.id)))).scalar() or 0
    no_phone = (await db.execute(
        select(func.count(Customer.id)).where(
            (Customer.phone.is_(None)) | (Customer.phone == "")
        )
    )).scalar() or 0
    no_email = (await db.execute(
        select(func.count(Customer.id)).where(
            (Customer.email.is_(None)) | (Customer.email == "")
        )
    )).scalar() or 0
    no_company = (await db.execute(
        select(func.count(Customer.id)).where(
            (Customer.company.is_(None)) | (Customer.company == "")
        )
    )).scalar() or 0

    # Quote completeness
    total_quotes = (await db.execute(select(func.count(Quote.id)))).scalar() or 0
    no_customer = (await db.execute(
        select(func.count(Quote.id)).where(Quote.customer_id.is_(None))
    )).scalar() or 0
    no_items = (await db.execute(
        select(func.count(Quote.id)).where(
            ~Quote.id.in_(select(QuoteItem.quote_id).distinct())
        )
    )).scalar() or 0

    return {
        "customers": {
            "total": total_customers,
            "missing_phone": no_phone,
            "missing_email": no_email,
            "missing_company": no_company,
            "completeness_pct": round((1 - (no_phone + no_company) / (total_customers * 2)) * 100, 1) if total_customers > 0 else 100,
        },
        "quotes": {
            "total": total_quotes,
            "missing_customer": no_customer,
            "missing_items": no_items,
            "completeness_pct": round((1 - (no_customer + no_items) / (total_quotes * 2)) * 100, 1) if total_quotes > 0 else 100,
        },
    }
