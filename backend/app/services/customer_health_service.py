"""Musteri saglik skoru hesaplama servisi.

Her musteri icin 0-100 arasi bir saglik skoru hesaplar.
Skor; teklif sikligi, yanit suresi, deger trendi, parca cesitliligi,
etkilesim guncelligi ve donusum orani gostergelerine dayanir.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer

logger = logging.getLogger(__name__)

HEALTHY_THRESHOLD = 70
AT_RISK_THRESHOLD = 40

LOOKBACK_DAYS = 180
TREND_RECENT_DAYS = 90
TREND_OLDER_DAYS = 180


@dataclass
class HealthIndicator:
    name: str
    label: str
    score: float
    weight: float
    raw_value: float | str
    description: str


@dataclass
class CustomerHealthReport:
    customer_id: int
    customer_name: str
    company: str | None
    score: int
    risk_level: str
    indicators: list[HealthIndicator] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


class CustomerHealthService:
    """Musteri saglik skoru hesaplayici."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def calculate_health_score(
        self, customer_id: int,
    ) -> CustomerHealthReport | None:
        """Tek bir musteri icin saglik raporu olusturur."""
        result = await self._db.execute(
            select(Customer).where(Customer.id == customer_id)
        )
        customer = result.scalar_one_or_none()
        if not customer:
            return None

        indicators = await self._compute_indicators(customer_id)
        total_weight = sum(i.weight for i in indicators)
        weighted_sum = sum(i.score * i.weight for i in indicators)
        raw_score = weighted_sum / total_weight if total_weight > 0 else 0
        score = max(0, min(100, round(raw_score)))

        risk_level = self._determine_risk_level(score)
        recommendations = self._generate_recommendations(indicators, risk_level)

        return CustomerHealthReport(
            customer_id=customer_id,
            customer_name=customer.name,
            company=customer.company,
            score=score,
            risk_level=risk_level,
            indicators=indicators,
            recommendations=recommendations,
        )

    async def get_all_health_scores(self) -> list[CustomerHealthReport]:
        """Tum musteriler icin saglik skorlarini hesaplar."""
        result = await self._db.execute(select(Customer.id))
        customer_ids = [row[0] for row in result.all()]

        reports = []
        for cid in customer_ids:
            report = await self.calculate_health_score(cid)
            if report:
                reports.append(report)

        reports.sort(key=lambda r: r.score)
        return reports

    async def get_at_risk_customers(
        self, limit: int = 10,
    ) -> list[CustomerHealthReport]:
        """Risk altindaki musterileri dondurur."""
        all_reports = await self.get_all_health_scores()
        at_risk = [r for r in all_reports if r.risk_level != "healthy"]
        return at_risk[:limit]

    async def _compute_indicators(
        self, customer_id: int,
    ) -> list[HealthIndicator]:
        """Alti temel gostergeyi hesaplar."""
        from app.services.health_indicators import (
            compute_quote_frequency,
            compute_response_time,
            compute_quote_value_trend,
            compute_parts_diversity,
            compute_engagement_recency,
            compute_conversion_rate,
        )

        now = datetime.now(timezone.utc)
        lookback = now - timedelta(days=LOOKBACK_DAYS)

        indicators = [
            await compute_quote_frequency(self._db, customer_id, lookback),
            await compute_response_time(self._db, customer_id, lookback),
            await compute_quote_value_trend(self._db, customer_id, now),
            await compute_parts_diversity(self._db, customer_id, lookback),
            await compute_engagement_recency(self._db, customer_id, now),
            await compute_conversion_rate(self._db, customer_id, lookback),
        ]
        return indicators

    @staticmethod
    def _determine_risk_level(score: int) -> str:
        if score >= HEALTHY_THRESHOLD:
            return "healthy"
        if score >= AT_RISK_THRESHOLD:
            return "at_risk"
        return "churning"

    @staticmethod
    def _generate_recommendations(
        indicators: list[HealthIndicator], risk_level: str,
    ) -> list[str]:
        """Gostergelere dayali oneriler uretir."""
        recommendations: list[str] = []
        indicator_map = {i.name: i for i in indicators}

        freq = indicator_map.get("quote_frequency")
        if freq and freq.score < 40:
            recommendations.append(
                "Teklif sikligi dusuk. Musteriye proaktif iletisim kurarak "
                "ihtiyaclarini sorgulayin."
            )

        response = indicator_map.get("response_time")
        if response and response.score < 40:
            recommendations.append(
                "Yanit suresi cok uzun. Email islem sureci hizlandirilmali."
            )

        trend = indicator_map.get("quote_value_trend")
        if trend and trend.score < 30:
            recommendations.append(
                "Teklif degeri dususte. Fiyat politikasini gozden gecirin "
                "veya ek urun onerileri sunun."
            )

        recency = indicator_map.get("engagement_recency")
        if recency and recency.score < 30:
            recommendations.append(
                "Uzun suredir etkilesim yok. Acil olarak musteri ile "
                "iletisime gecin."
            )

        conversion = indicator_map.get("conversion_rate")
        if conversion and conversion.score < 40:
            recommendations.append(
                "Donusum orani dusuk. Teklif kalitesini ve fiyatlandirmayi "
                "gozden gecirin."
            )

        diversity = indicator_map.get("parts_diversity")
        if diversity and diversity.score < 40:
            recommendations.append(
                "Parca cesitliligi az. Capraz satis firsatlarini degerlendirin."
            )

        if risk_level == "churning" and not recommendations:
            recommendations.append(
                "Musteri kayip riski yuksek. Ozel kampanya veya "
                "toplanti planlayarak iliskiyi canlandirin."
            )

        return recommendations
