"""Musteri saglik gosterge hesaplayicilari.

Her fonksiyon tek bir HealthIndicator dondurur.
CustomerHealthService bu modulu kullanarak toplam skoru hesaplar.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_request import EmailRequest
from app.models.quote import Quote
from app.models.quote_item import QuoteItem

from app.services.customer_health_service import (
    HealthIndicator,
    LOOKBACK_DAYS,
    TREND_RECENT_DAYS,
    TREND_OLDER_DAYS,
)


async def compute_quote_frequency(
    db: AsyncSession, customer_id: int, lookback: datetime,
) -> HealthIndicator:
    """Son 6 ayda aylik ortalama teklif sayisi."""
    result = await db.execute(
        select(func.count(Quote.id)).where(
            and_(Quote.customer_id == customer_id, Quote.created_at >= lookback)
        )
    )
    count = result.scalar() or 0
    months = LOOKBACK_DAYS / 30
    monthly_avg = count / months if months > 0 else 0

    score = min(100, monthly_avg * 50)

    return HealthIndicator(
        name="quote_frequency",
        label="Teklif Sikligi",
        score=score,
        weight=0.20,
        raw_value=round(monthly_avg, 1),
        description=f"Aylik ortalama {round(monthly_avg, 1)} teklif",
    )


async def compute_response_time(
    db: AsyncSession, customer_id: int, lookback: datetime,
) -> HealthIndicator:
    """Email'den teklife ortalama gecis suresi (saat)."""
    result = await db.execute(
        select(
            func.avg(
                func.extract(
                    "epoch",
                    Quote.created_at - EmailRequest.received_at,
                ) / 3600
            )
        )
        .join(EmailRequest, Quote.email_request_id == EmailRequest.id)
        .where(
            and_(
                Quote.customer_id == customer_id,
                Quote.created_at >= lookback,
                EmailRequest.received_at.isnot(None),
            )
        )
    )
    avg_hours = result.scalar()

    if avg_hours is None:
        return HealthIndicator(
            name="response_time",
            label="Yanit Suresi",
            score=50,
            weight=0.15,
            raw_value="N/A",
            description="Yeterli veri yok",
        )

    MAX_HOURS = 48
    MIN_HOURS = 4
    clamped = max(MIN_HOURS, min(MAX_HOURS, avg_hours))
    score = 100 * (MAX_HOURS - clamped) / (MAX_HOURS - MIN_HOURS)

    return HealthIndicator(
        name="response_time",
        label="Yanit Suresi",
        score=score,
        weight=0.15,
        raw_value=round(avg_hours, 1),
        description=f"Ortalama {round(avg_hours, 1)} saat",
    )


async def compute_quote_value_trend(
    db: AsyncSession, customer_id: int, now: datetime,
) -> HealthIndicator:
    """Son 3 ay vs onceki 3 ay teklif degeri trendi."""
    recent_start = now - timedelta(days=TREND_RECENT_DAYS)
    older_start = now - timedelta(days=TREND_OLDER_DAYS)

    recent_q = await db.execute(
        select(func.coalesce(func.sum(Quote.grand_total), 0.0)).where(
            and_(Quote.customer_id == customer_id, Quote.created_at >= recent_start)
        )
    )
    recent_value = recent_q.scalar() or 0.0

    older_q = await db.execute(
        select(func.coalesce(func.sum(Quote.grand_total), 0.0)).where(
            and_(
                Quote.customer_id == customer_id,
                Quote.created_at >= older_start,
                Quote.created_at < recent_start,
            )
        )
    )
    older_value = older_q.scalar() or 0.0

    if older_value == 0 and recent_value == 0:
        score = 30.0
        trend_pct = 0.0
    elif older_value == 0:
        score = 100.0
        trend_pct = 100.0
    else:
        trend_pct = ((recent_value - older_value) / older_value) * 100
        score = max(0, min(100, 50 + trend_pct))

    return HealthIndicator(
        name="quote_value_trend",
        label="Deger Trendi",
        score=score,
        weight=0.20,
        raw_value=f"%{round(trend_pct, 1)}",
        description=f"Son 3 ay degisim: %{round(trend_pct, 1)}",
    )


async def compute_parts_diversity(
    db: AsyncSession, customer_id: int, lookback: datetime,
) -> HealthIndicator:
    """Farkli parca kodu cesitliligi."""
    result = await db.execute(
        select(func.count(func.distinct(QuoteItem.honeywell_code)))
        .join(Quote, QuoteItem.quote_id == Quote.id)
        .where(
            and_(
                Quote.customer_id == customer_id,
                Quote.created_at >= lookback,
                QuoteItem.honeywell_code.isnot(None),
            )
        )
    )
    unique_parts = result.scalar() or 0

    DIVERSITY_TARGET = 10
    score = min(100, (unique_parts / DIVERSITY_TARGET) * 100)

    return HealthIndicator(
        name="parts_diversity",
        label="Parca Cesitliligi",
        score=score,
        weight=0.10,
        raw_value=unique_parts,
        description=f"{unique_parts} farkli parca",
    )


async def compute_engagement_recency(
    db: AsyncSession, customer_id: int, now: datetime,
) -> HealthIndicator:
    """Son etkilesimden bu yana gecen gun sayisi."""
    latest_quote = await db.execute(
        select(func.max(Quote.created_at)).where(Quote.customer_id == customer_id)
    )
    latest_email = await db.execute(
        select(func.max(EmailRequest.created_at)).where(
            EmailRequest.customer_id == customer_id
        )
    )

    last_quote_date = latest_quote.scalar()
    last_email_date = latest_email.scalar()

    dates = [d for d in [last_quote_date, last_email_date] if d is not None]
    if not dates:
        return HealthIndicator(
            name="engagement_recency",
            label="Etkilesim Guncelligi",
            score=0,
            weight=0.20,
            raw_value="Hic",
            description="Hicbir etkilesim bulunamadi",
        )

    last_activity = max(dates)
    if last_activity.tzinfo is None:
        last_activity = last_activity.replace(tzinfo=timezone.utc)

    days_since = (now - last_activity).days

    MAX_INACTIVE_DAYS = 90
    MIN_INACTIVE_DAYS = 7
    if days_since <= MIN_INACTIVE_DAYS:
        score = 100.0
    elif days_since >= MAX_INACTIVE_DAYS:
        score = 0.0
    else:
        score = 100 * (MAX_INACTIVE_DAYS - days_since) / (
            MAX_INACTIVE_DAYS - MIN_INACTIVE_DAYS
        )

    return HealthIndicator(
        name="engagement_recency",
        label="Etkilesim Guncelligi",
        score=score,
        weight=0.20,
        raw_value=f"{days_since} gun",
        description=f"Son etkilesim {days_since} gun once",
    )


async def compute_conversion_rate(
    db: AsyncSession, customer_id: int, lookback: datetime,
) -> HealthIndicator:
    """Gonderilen/kabul edilen teklif orani."""
    total_q = await db.execute(
        select(func.count(Quote.id)).where(
            and_(Quote.customer_id == customer_id, Quote.created_at >= lookback)
        )
    )
    total = total_q.scalar() or 0

    converted_q = await db.execute(
        select(func.count(Quote.id)).where(
            and_(
                Quote.customer_id == customer_id,
                Quote.created_at >= lookback,
                Quote.status.in_(["sent", "accepted"]),
            )
        )
    )
    converted = converted_q.scalar() or 0

    if total == 0:
        return HealthIndicator(
            name="conversion_rate",
            label="Donusum Orani",
            score=30,
            weight=0.15,
            raw_value="N/A",
            description="Henuz teklif yok",
        )

    rate = (converted / total) * 100
    score = min(100, rate * 1.25)

    return HealthIndicator(
        name="conversion_rate",
        label="Donusum Orani",
        score=score,
        weight=0.15,
        raw_value=f"%{round(rate, 1)}",
        description=f"Tekliflerin %{round(rate, 1)}'i donusturuldu",
    )
