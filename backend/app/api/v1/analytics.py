from __future__ import annotations

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
from app.schemas.spare_part import MissingPricePartResponse
from app.schemas.analytics import (
    ActivityDroughtResponse,
    AIQualityResponse,
    AIUsageResponse,
    CategoryBreakdownItem,
    DataQualityResponse,
    DealVelocityResponse,
    DiscountGuardrailsResponse,
    DiscountsResponse,
    ForecastResponse,
    FunnelResponse,
    MonthlyTrendItem,
    PipelineWeeklyDiffResponse,
    RecordQualityResponse,
    RepScorecardsResponse,
    RevenueLeaksResponse,
    SLAResponse,
    SlippageResponse,
    TopPartItem,
    WaterfallResponse,
    WinLossDetailResponse,
    WinLossReasonsResponse,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/top-parts", response_model=list[TopPartItem])
async def get_top_parts(
    days: int = Query(30, ge=1, le=365, description="Lookback period in days"),
    limit: int = Query(10, ge=1, le=100, description="Number of results"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Top requested parts by quote item count — single JOIN query (no N+1)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(
            QuoteItem.honeywell_code,
            func.count(QuoteItem.id).label("request_count"),
            func.sum(QuoteItem.quantity).label("total_quantity"),
            func.sum(QuoteItem.line_total).label("total_value"),
            SparePart.name_en,
            SparePart.name_tr,
            SparePart.category,
        )
        .join(Quote, QuoteItem.quote_id == Quote.id)
        .outerjoin(SparePart, SparePart.honeywell_code == QuoteItem.honeywell_code)
        .where(Quote.created_at >= cutoff)
        .where(QuoteItem.honeywell_code.isnot(None))
        .group_by(QuoteItem.honeywell_code, SparePart.name_en, SparePart.name_tr, SparePart.category)
        .order_by(func.count(QuoteItem.id).desc())
        .limit(limit)
    )
    rows = result.all()

    return [
        {
            "honeywell_code": row.honeywell_code,
            "request_count": row.request_count,
            "total_quantity": row.total_quantity or 0,
            "total_value": round(row.total_value or 0, 2),
            "name_en": row.name_en,
            "name_tr": row.name_tr,
            "category": row.category,
        }
        for row in rows
    ]


@router.get("/monthly-trend", response_model=list[MonthlyTrendItem])
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


@router.get("/category-breakdown", response_model=list[CategoryBreakdownItem])
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


@router.get(
    "/parts-without-price",
    response_model=list[MissingPricePartResponse],
)
async def get_parts_without_price(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Parts requested in quotes that have no pricing (supplier_price AND transfer_price both null).

    Round-15 audit F-027 — ``response_model`` wired. Two row variants:
      * ``no_price``     — part exists, pricing fields are NULL.
      * ``unknown_part`` — quoted SKU absent from the catalog.
    """
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


@router.get("/ai-usage", response_model=AIUsageResponse)
async def get_ai_usage(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """AI usage statistics: parse counts, correction rates, model performance."""
    return await _compute_ai_metrics(db)


@router.get("/ai-quality", response_model=AIQualityResponse)
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


@router.get("/forecast", response_model=ForecastResponse)
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


@router.get("/slippage", response_model=SlippageResponse)
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


@router.get("/funnel", response_model=FunnelResponse)
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


@router.get("/rep-scorecards", response_model=RepScorecardsResponse)
async def get_rep_scorecards(
    window: int = Query(30, ge=1, le=365),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Feature-5: Rep performance scorecards — single aggregate query (no N+1)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    # Single query: GROUP BY created_by with conditional counts
    result = await db.execute(
        select(
            Quote.created_by,
            User.full_name,
            User.role,
            func.count(Quote.id).label("quote_count"),
            func.count(case((Quote.status == "sent", Quote.id))).label("sent_count"),
            func.count(case((Quote.status == "approved", Quote.id))).label("approved_count"),
            func.count(case((Quote.status == "accepted", Quote.id))).label("won_count"),
            func.coalesce(func.sum(Quote.grand_total), 0.0).label("revenue"),
            func.coalesce(func.avg(case((Quote.discount_total > 0, Quote.discount_total))), 0.0).label("avg_discount"),
        )
        .join(User, Quote.created_by == User.id)
        .where(Quote.created_at >= cutoff)
        .where(User.is_active.is_(True))
        .where(User.role.in_(["sales_rep", "sales_manager"]))
        .group_by(Quote.created_by, User.full_name, User.role)
        .order_by(func.sum(Quote.grand_total).desc())
    )
    rows = result.all()

    scorecards = []
    for r in rows:
        total = r.quote_count
        won = r.won_count
        win_rate = round(won / total * 100, 1) if total > 0 else 0
        scorecards.append({
            "user_id": r.created_by,
            "full_name": r.full_name,
            "role": r.role,
            "quote_count": total,
            "sent_count": r.sent_count,
            "approved_count": r.approved_count,
            "won_count": won,
            "win_rate": win_rate,
            "revenue": round(float(r.revenue), 2),
            "avg_discount": round(float(r.avg_discount), 2),
        })

    return {"window_days": window, "scorecards": scorecards}


@router.get("/discounts", response_model=DiscountsResponse)
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


@router.get("/sla", response_model=SLAResponse)
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


@router.get("/win-loss-reasons", response_model=WinLossReasonsResponse)
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


@router.get("/data-quality", response_model=DataQualityResponse)
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

    cust_pct = round((1 - (no_phone + no_company) / (total_customers * 2)) * 100, 1) if total_customers > 0 else 100
    quote_pct = round((1 - (no_customer + no_items) / (total_quotes * 2)) * 100, 1) if total_quotes > 0 else 100
    avg_score = round((cust_pct + quote_pct) / 2, 1)

    return {
        "data": {
            "avg_score": avg_score,
        },
        "customers": {
            "total": total_customers,
            "missing_phone": no_phone,
            "missing_email": no_email,
            "missing_company": no_company,
            "completeness_pct": cust_pct,
        },
        "quotes": {
            "total": total_quotes,
            "missing_customer": no_customer,
            "missing_items": no_items,
            "completeness_pct": quote_pct,
        },
    }


@router.get("/pipeline-weekly-diff", response_model=PipelineWeeklyDiffResponse)
async def get_pipeline_weekly_diff(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """What changed in pipeline since last week."""
    from app.models.opportunity import Opportunity

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # New opportunities this week
    new_opps = (await db.execute(
        select(func.count(Opportunity.id)).where(Opportunity.created_at >= week_ago)
    )).scalar() or 0

    # Stage changes this week (from events)
    from app.models.opportunity import OpportunityEvent
    stage_changes = (await db.execute(
        select(func.count(OpportunityEvent.id)).where(
            OpportunityEvent.event_type == "stage_change",
            OpportunityEvent.occurred_at >= week_ago,
        )
    )).scalar() or 0

    # Quotes created this week
    new_quotes = (await db.execute(
        select(func.count(Quote.id)).where(Quote.created_at >= week_ago)
    )).scalar() or 0

    # Pipeline value change
    current_pipeline = (await db.execute(
        select(func.coalesce(func.sum(Opportunity.amount), 0.0)).where(
            Opportunity.status == "active"
        )
    )).scalar() or 0

    return {
        "period": "son 7 gun",
        "new_opportunities": new_opps,
        "stage_changes": stage_changes,
        "new_quotes": new_quotes,
        "current_pipeline_total": round(float(current_pipeline), 2),
    }


@router.get("/discount-guardrails", response_model=DiscountGuardrailsResponse)
async def get_discount_guardrails(
    window: int = Query(30, ge=1, le=365),
    threshold_pct: float = Query(20.0),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Discount guardrails: quotes exceeding threshold → needs approval routing."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    # Quotes with high discount
    q = await db.execute(
        select(
            Quote.id, Quote.quote_number, Quote.subtotal, Quote.discount_total,
            Quote.grand_total, Quote.status, Quote.created_by,
        )
        .where(Quote.created_at >= cutoff, Quote.subtotal > 0)
    )
    rows = q.all()

    flagged = []
    for r in rows:
        rate = round((r.discount_total / r.subtotal) * 100, 1) if r.subtotal > 0 else 0
        if rate >= threshold_pct:
            flagged.append({
                "id": r.id,
                "quote_number": r.quote_number,
                "discount_rate": rate,
                "discount_total": round(r.discount_total, 2),
                "grand_total": round(r.grand_total, 2),
                "status": r.status,
                "needs_approval": r.status == "draft",
            })

    return {
        "threshold_pct": threshold_pct,
        "flagged_count": len(flagged),
        "flagged_quotes": flagged,
    }


# ══════════════════════════════════════════════════════════════
# FAZ-3 PIPELINE DEPTH ANALYTICS
# ══════════════════════════════════════════════════════════════


@router.get("/deal-velocity", response_model=DealVelocityResponse)
async def deal_velocity(
    window: int = Query(90, ge=7, le=365),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Avg days per stage, total cycle time, stage-to-stage conversion rates."""
    from app.models.opportunity import Opportunity, OpportunityEvent

    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    # Stage change events in window
    events_q = await db.execute(
        select(
            OpportunityEvent.opportunity_id,
            OpportunityEvent.description,
            OpportunityEvent.occurred_at,
        )
        .where(
            OpportunityEvent.event_type == "stage_change",
            OpportunityEvent.occurred_at >= cutoff,
        )
        .order_by(
            OpportunityEvent.opportunity_id,
            OpportunityEvent.occurred_at.asc(),
        )
    )
    events = events_q.all()

    # Group events by opportunity
    opp_events: dict[int, list] = {}
    for event in events:
        opp_events.setdefault(event.opportunity_id, []).append(event)

    # Calculate time per stage from consecutive stage_change events
    stage_durations: dict[str, list[float]] = {}
    total_cycle_days: list[float] = []

    for opp_id, opp_event_list in opp_events.items():
        first_event_time = opp_event_list[0].occurred_at
        last_event_time = opp_event_list[-1].occurred_at

        if first_event_time and last_event_time:
            if first_event_time.tzinfo is None:
                first_event_time = first_event_time.replace(tzinfo=timezone.utc)
            if last_event_time.tzinfo is None:
                last_event_time = last_event_time.replace(tzinfo=timezone.utc)
            cycle = (last_event_time - first_event_time).total_seconds() / 86400.0
            if cycle > 0:
                total_cycle_days.append(cycle)

        for i in range(len(opp_event_list) - 1):
            current_evt = opp_event_list[i]
            next_evt = opp_event_list[i + 1]

            # Extract stage from description "Asamadan gecis: X -> Y"
            from_stage = _extract_from_stage(current_evt.description)
            if not from_stage:
                continue

            t1 = current_evt.occurred_at
            t2 = next_evt.occurred_at
            if t1 and t2:
                if t1.tzinfo is None:
                    t1 = t1.replace(tzinfo=timezone.utc)
                if t2.tzinfo is None:
                    t2 = t2.replace(tzinfo=timezone.utc)
                days = (t2 - t1).total_seconds() / 86400.0
                if days >= 0:
                    stage_durations.setdefault(from_stage, []).append(days)

    # Avg days per stage
    avg_days_per_stage = {
        stage: round(sum(durations) / len(durations), 1)
        for stage, durations in stage_durations.items()
        if durations
    }

    avg_cycle_time = (
        round(sum(total_cycle_days) / len(total_cycle_days), 1)
        if total_cycle_days
        else 0.0
    )

    # Stage-to-stage conversion rates from opportunity counts
    stage_order = ["prospecting", "qualified", "proposal", "negotiation", "closed_won"]
    stage_counts_q = await db.execute(
        select(Opportunity.stage, func.count(Opportunity.id))
        .where(Opportunity.created_at >= cutoff)
        .group_by(Opportunity.stage)
    )
    stage_counts = {row[0]: row[1] for row in stage_counts_q.all()}

    conversions = []
    for i in range(len(stage_order) - 1):
        from_stage = stage_order[i]
        to_stage = stage_order[i + 1]
        from_count = sum(
            stage_counts.get(s, 0) for s in stage_order[i:]
        )
        to_count = sum(
            stage_counts.get(s, 0) for s in stage_order[i + 1:]
        )
        rate = round(to_count / from_count * 100, 1) if from_count > 0 else 0.0
        conversions.append({
            "from_stage": from_stage,
            "to_stage": to_stage,
            "rate": rate,
        })

    return {
        "window_days": window,
        "avg_days_per_stage": avg_days_per_stage,
        "avg_cycle_time_days": avg_cycle_time,
        "conversions": conversions,
    }


def _extract_from_stage(description: str | None) -> str | None:
    """Extract source stage from event description like 'Asamadan gecis: X -> Y'."""
    if not description:
        return None
    if " -> " in description:
        parts = description.split(" -> ")
        from_part = parts[0].split(": ")
        if len(from_part) > 1:
            return from_part[-1].strip()
    return None


@router.get("/win-loss-detail", response_model=WinLossDetailResponse)
async def win_loss_detail(
    window: int = Query(90, ge=7, le=365),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Win rate by owner, by source, avg deal size won vs lost, top loss reasons."""
    from app.models.opportunity import Opportunity

    cutoff = datetime.now(timezone.utc) - timedelta(days=window)
    closed_filter = and_(
        Opportunity.stage.in_(["closed_won", "closed_lost"]),
        Opportunity.updated_at >= cutoff,
    )

    # Win rate by owner
    owner_q = await db.execute(
        select(
            Opportunity.owner_id,
            User.full_name,
            func.count(Opportunity.id).label("total"),
            func.count(
                case((Opportunity.stage == "closed_won", Opportunity.id))
            ).label("won"),
            func.coalesce(
                func.sum(
                    case((Opportunity.stage == "closed_won", Opportunity.amount))
                ),
                0.0,
            ).label("won_value"),
            func.coalesce(
                func.sum(
                    case((Opportunity.stage == "closed_lost", Opportunity.amount))
                ),
                0.0,
            ).label("lost_value"),
        )
        .join(User, Opportunity.owner_id == User.id)
        .where(closed_filter)
        .group_by(Opportunity.owner_id, User.full_name)
        .order_by(func.count(Opportunity.id).desc())
    )
    owner_rows = owner_q.all()

    by_owner = [
        {
            "owner_id": r.owner_id,
            "full_name": r.full_name,
            "total": r.total,
            "won": r.won,
            "win_rate": round(r.won / r.total * 100, 1) if r.total > 0 else 0.0,
            "won_value": round(float(r.won_value), 2),
            "lost_value": round(float(r.lost_value), 2),
        }
        for r in owner_rows
    ]

    # Avg deal size won vs lost
    avg_q = await db.execute(
        select(
            Opportunity.stage,
            func.coalesce(func.avg(Opportunity.amount), 0.0).label("avg_amount"),
            func.count(Opportunity.id).label("count"),
        )
        .where(closed_filter)
        .group_by(Opportunity.stage)
    )
    avg_rows = {r.stage: {"avg_amount": round(float(r.avg_amount), 2), "count": r.count} for r in avg_q.all()}

    # Top loss reasons
    loss_reasons_q = await db.execute(
        select(
            Opportunity.loss_reason,
            func.count(Opportunity.id).label("count"),
            func.coalesce(func.sum(Opportunity.amount), 0.0).label("total_value"),
        )
        .where(
            Opportunity.stage == "closed_lost",
            Opportunity.updated_at >= cutoff,
            Opportunity.loss_reason.isnot(None),
        )
        .group_by(Opportunity.loss_reason)
        .order_by(func.count(Opportunity.id).desc())
        .limit(10)
    )
    loss_reasons = [
        {
            "reason": r.loss_reason,
            "count": r.count,
            "total_value": round(float(r.total_value), 2),
        }
        for r in loss_reasons_q.all()
    ]

    # Overall win rate
    total_closed = sum(r.total for r in owner_rows)
    total_won = sum(r.won for r in owner_rows)
    overall_win_rate = (
        round(total_won / total_closed * 100, 1) if total_closed > 0 else 0.0
    )

    return {
        "window_days": window,
        "overall_win_rate": overall_win_rate,
        "total_closed": total_closed,
        "total_won": total_won,
        "by_owner": by_owner,
        "avg_deal_size": {
            "closed_won": avg_rows.get("closed_won", {"avg_amount": 0, "count": 0}),
            "closed_lost": avg_rows.get("closed_lost", {"avg_amount": 0, "count": 0}),
        },
        "top_loss_reasons": loss_reasons,
    }


# ══════════════════════════════════════════════════════════════
# MODUL 6: ACTIVITY DROUGHT
# ══════════════════════════════════════════════════════════════


@router.get("/activity-drought", response_model=ActivityDroughtResponse)
async def get_activity_drought(
    days: int = Query(7, ge=1, le=90, description="Days without activity"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Opportunities with no activity for X days."""
    from app.models.activity_log import ActivityLog
    from app.models.opportunity import Opportunity
    from app.models.user import User as UserModel

    now = datetime.now(timezone.utc)
    threshold = now - timedelta(days=days)

    # Subquery: last activity per opportunity
    last_activity_sq = (
        select(
            ActivityLog.opportunity_id,
            func.max(ActivityLog.created_at).label("last_at"),
        )
        .where(ActivityLog.opportunity_id.isnot(None))
        .group_by(ActivityLog.opportunity_id)
        .subquery()
    )

    # RBAC scoping
    conditions = [Opportunity.status == "active"]
    if current_user.role == UserRole.SALES_REP.value:
        conditions.append(Opportunity.owner_id == current_user.id)

    # Opportunities where last activity is before threshold OR no activity at all
    query = (
        select(
            Opportunity.id,
            Opportunity.title,
            Opportunity.stage,
            Opportunity.owner_id,
            last_activity_sq.c.last_at,
        )
        .outerjoin(last_activity_sq, Opportunity.id == last_activity_sq.c.opportunity_id)
        .where(
            and_(
                *conditions,
                (last_activity_sq.c.last_at < threshold) | (last_activity_sq.c.last_at.is_(None)),
            )
        )
        .order_by(last_activity_sq.c.last_at.asc().nullsfirst())
    )

    result = await db.execute(query)
    rows = result.all()

    # Enrich with owner names
    owner_ids = list({r.owner_id for r in rows if r.owner_id})
    owner_map: dict[int, str] = {}
    if owner_ids:
        owners_q = await db.execute(
            select(UserModel.id, UserModel.full_name).where(UserModel.id.in_(owner_ids))
        )
        owner_map = {u.id: u.full_name for u in owners_q.all()}

    items = []
    for row in rows:
        if row.last_at:
            last_at = row.last_at
            if last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
            days_since = (now - last_at).days
        else:
            days_since = 999

        items.append({
            "id": row.id,
            "title": row.title,
            "stage": row.stage,
            "days_since_last": days_since,
            "owner_name": owner_map.get(row.owner_id, ""),
        })

    return {"items": items, "total": len(items)}


# ── Data Quality ──────────────────────────────────────
# NOTE: /data-quality list endpoint is defined earlier (~line 701) with
# SALES_MANAGER role guard. The previous duplicate here was removed to
# prevent privilege escalation via route-ordering bugs.


@router.get("/data-quality/{entity_type}/{entity_id}", response_model=RecordQualityResponse)
async def get_record_quality(
    entity_type: str,
    entity_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Single record quality score."""
    from app.core.exceptions import NotFoundException
    from app.models.opportunity import Opportunity as OppModel
    from app.services.data_quality_service import DataQualityService
    from app.services.tenant_context import assert_same_tenant

    service = DataQualityService(db)

    if entity_type == "customer":
        record = (await db.execute(
            select(Customer).where(Customer.id == entity_id)
        )).scalar_one_or_none()
        if not record:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Musteri bulunamadi")
        # R4-TEN-22: drill-down loads by id must be tenant-scoped. Cross-
        # tenant attempts collapse to the same 404 so the API can't be
        # used for ID enumeration across tenants.
        try:
            assert_same_tenant(record, current_user, exception_cls=NotFoundException)
        except NotFoundException:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Musteri bulunamadi")
        result = await service.score_customer(record)
    elif entity_type == "opportunity":
        record = (await db.execute(
            select(OppModel).where(OppModel.id == entity_id)
        )).scalar_one_or_none()
        if not record:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Firsat bulunamadi")
        # R4-TEN-22: same cross-tenant guard for the opportunity branch.
        try:
            assert_same_tenant(record, current_user, exception_cls=NotFoundException)
        except NotFoundException:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Firsat bulunamadi")
        result = await service.score_opportunity(record)
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Gecersiz entity_type: customer veya opportunity")

    return {"data": result}


# ══════════════════════════════════════════════════════════════
# MODUL 5: REVENUE WATERFALL
# ══════════════════════════════════════════════════════════════


@router.get("/waterfall", response_model=WaterfallResponse)
async def get_revenue_waterfall(
    from_date: str = None,
    to_date: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revenue waterfall: pipeline movement between two dates."""
    from app.services.revenue_waterfall_service import RevenueWaterfallService

    if not from_date:
        to_dt = datetime.now(timezone.utc)
        from_dt = to_dt - timedelta(days=30)
        from_date = from_dt.isoformat()
        to_date = to_dt.isoformat()

    service = RevenueWaterfallService(db)
    result = await service.get_waterfall(from_date, to_date)
    return {"data": result}


# ══════════════════════════════════════════════════════════════
# MODUL 10: REVENUE LEAK DETECTION
# ══════════════════════════════════════════════════════════════


@router.get("/revenue-leaks", response_model=RevenueLeaksResponse)
async def get_revenue_leaks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revenue leak detection: scan active opportunities for leak indicators."""
    from app.services.leak_detection_service import LeakDetectionService

    service = LeakDetectionService(db)
    result = await service.detect_leaks()
    return {"data": result}
