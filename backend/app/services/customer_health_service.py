"""Musteri saglik skoru hesaplama servisi.

Her musteri icin 0-100 arasi bir saglik skoru hesaplar.
Skor; teklif sikligi, yanit suresi, deger trendi, parca cesitliligi,
etkilesim guncelligi ve donusum orani gostergelerine dayanir.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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

    def __post_init__(self) -> None:
        # Postgres aggregates (SUM/AVG on NUMERIC columns) return Decimal
        # via asyncpg. Score downstream is multiplied by `weight: float`,
        # and Decimal * float raises TypeError. Coerce here so every
        # compute_* function stays free to pass whatever SQLAlchemy hands
        # back without each one needing its own cast.
        if not isinstance(self.score, float):
            self.score = float(self.score)
        if not isinstance(self.weight, float):
            self.weight = float(self.weight)


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
        """Tum musteriler icin saglik skorlarini hesaplar.

        Optimized: loads all customers in a single query, then computes
        indicators per customer (still N queries for indicators — full
        batch optimization is a larger refactor tracked separately).

        Resilience: per-customer indicator computation is wrapped so one
        bad row (missing FK target, unexpected null, mid-migration drift,
        etc.) cannot take down the whole cockpit. Broken customers are
        logged and skipped rather than 500'ing the endpoint.
        """
        result = await self._db.execute(select(Customer))
        customers = result.scalars().all()

        reports = []
        for customer in customers:
            try:
                indicators = await self._compute_indicators(customer.id)
                total_weight = sum(i.weight for i in indicators)
                weighted_sum = sum(i.score * i.weight for i in indicators)
                raw_score = weighted_sum / total_weight if total_weight > 0 else 0
                score = max(0, min(100, round(raw_score)))

                risk_level = self._determine_risk_level(score)
                recommendations = self._generate_recommendations(indicators, risk_level)

                reports.append(CustomerHealthReport(
                    customer_id=customer.id,
                    customer_name=customer.name,
                    company=customer.company,
                    score=score,
                    risk_level=risk_level,
                    indicators=indicators,
                    recommendations=recommendations,
                ))
            except Exception:
                logger.exception(
                    "customer_health_compute_failed customer_id=%s", customer.id,
                )
                # Skip this customer and keep going. Prevents a single bad row
                # (missing FK target, unexpected null) from 500'ing /risky-accounts.
                continue

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

    async def predict_churn_risk(self, customer_id: int) -> dict:
        """Predict churn risk for a customer using Claude AI or rule-based fallback.

        Returns {churn_probability, risk_level, risk_factors, retention_actions}.
        """
        health_report = await self.calculate_health_score(customer_id)
        if not health_report:
            return {"error": "Musteri bulunamadi"}

        health_data = {
            "customer_id": health_report.customer_id,
            "customer_name": health_report.customer_name,
            "company": health_report.company,
            "score": health_report.score,
            "risk_level": health_report.risk_level,
            "indicators": [
                {
                    "name": ind.name,
                    "label": ind.label,
                    "score": ind.score,
                    "raw_value": str(ind.raw_value),
                    "description": ind.description,
                }
                for ind in health_report.indicators
            ],
            "recommendations": health_report.recommendations,
        }

        # Strategy 1: Claude AI prediction
        if settings.ANTHROPIC_API_KEY:
            ai_result = await self._claude_churn_prediction(health_data)
            if ai_result:
                return ai_result

        # Strategy 2: Rule-based fallback
        return self._rule_based_churn_prediction(health_data)

    async def _claude_churn_prediction(self, health_data: dict) -> dict | None:
        """Use Claude for churn risk prediction."""
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

            indicators_text = "\n".join(
                f"- {ind['label']}: {ind['score']}/100 ({ind['description']})"
                for ind in health_data["indicators"]
            )

            prompt = (
                f"Musteri: {health_data['customer_name']}\n"
                f"Sirket: {health_data['company'] or 'Bilinmiyor'}\n"
                f"Saglik Skoru: {health_data['score']}/100\n"
                f"Risk Seviyesi: {health_data['risk_level']}\n\n"
                f"Gostergeler:\n{indicators_text}\n\n"
                "Bu musterinin kayip (churn) riskini degerlendir. JSON formatinda cevap ver:\n"
                '{"churn_probability": 0-100, "risk_level": "high|medium|low", '
                '"risk_factors": [{"name": "...", "description": "..."}], '
                '"retention_actions": ["..."]}'
            )

            response = await client.messages.create(
                model=settings.AI_MODEL_NAME,
                max_tokens=512,
                system=(
                    "Sen bir musteri kayip analiz asistanisin. Musteri verilerini "
                    "inceleyerek kayip riskini degerlendir ve elde tutma onerileri sun."
                ),
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text if response.content else None
            if text:
                parsed = json.loads(text.strip())
                valid_levels = {"high", "medium", "low"}
                if parsed.get("risk_level") in valid_levels:
                    return {
                        "customer_id": health_data["customer_id"],
                        "churn_probability": min(100, max(0, int(parsed.get("churn_probability", 50)))),
                        "risk_level": parsed["risk_level"],
                        "risk_factors": parsed.get("risk_factors", []),
                        "retention_actions": parsed.get("retention_actions", []),
                        "method": "ai",
                    }
        except Exception as exc:
            logger.error("Claude churn prediction hatasi: %s", exc)

        return None

    @staticmethod
    def _rule_based_churn_prediction(health_data: dict) -> dict:
        """Rule-based churn risk prediction fallback."""
        score = health_data["score"]
        risk_factors = []
        retention_actions = []

        # Determine churn probability inversely from health score
        churn_probability = max(0, min(100, 100 - score))

        # Determine risk level
        if score < 40:
            risk_level = "high"
        elif score < 60:
            risk_level = "medium"
        else:
            risk_level = "low"

        # Analyze indicators for specific risk factors
        for ind in health_data["indicators"]:
            if ind["score"] < 40:
                risk_factors.append({
                    "name": ind["label"],
                    "description": ind["description"],
                })

        # Generate retention actions based on risk level
        if risk_level == "high":
            retention_actions.extend([
                "Acil olarak musteri ile yuz yuze toplanti planlayin.",
                "Ozel indirim veya kampanya teklifi hazirlayip sunun.",
                "Ust duzey yonetici ile iletisim kanalini acin.",
            ])
        elif risk_level == "medium":
            retention_actions.extend([
                "Musteri ile duzenli check-in gorusmeleri baslantin.",
                "Memnuniyet anketi gondererek geri bildirim alin.",
                "Capraz satis firsatlarini degerlendirin.",
            ])
        else:
            retention_actions.append(
                "Mevcut iliskiyi koruyun ve proaktif iletisimi surdurun."
            )

        # Add specific actions from recommendations
        for rec in health_data.get("recommendations", []):
            if rec not in retention_actions:
                retention_actions.append(rec)

        return {
            "customer_id": health_data["customer_id"],
            "churn_probability": churn_probability,
            "risk_level": risk_level,
            "risk_factors": risk_factors,
            "retention_actions": retention_actions,
            "method": "rule_based",
        }

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
