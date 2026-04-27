"""AI deal risk scoring — Claude-powered risk assessment with explainable factors."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.circuit_breaker import CircuitOpenError
from app.core.claude_client import claude_messages_create
from app.core.config import settings
from app.models.activity_log import ActivityLog
from app.models.opportunity import Opportunity, OpportunitySignal
from app.models.quote import Quote
from app.services.llm_json import parse_claude_json

logger = logging.getLogger(__name__)

RISK_WEIGHTS = {
    "no_activity": 25,
    "negative_signals": 20,
    "no_quotes": 15,
    "stale_deal": 20,
    "low_health_score": 20,
}


async def assess_deal_risk(db: AsyncSession, opportunity_id: int) -> dict:
    """Claude-powered deal risk assessment with explainable factors.

    Gathers: signals, health, events, quotes, activities.
    Returns {risk_score: 0-100, risk_level, factors: [{name, impact, evidence}], recommendations: []}.
    """
    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()

    if not opp:
        return {"error": "Firsat bulunamadi"}

    # Gather context
    context = await _gather_deal_context(db, opp)

    # Strategy 1: Claude AI assessment
    if settings.ANTHROPIC_API_KEY:
        ai_result = await _claude_risk_assessment(opp, context)
        if ai_result:
            return ai_result

    # Strategy 2: Rule-based fallback
    return _rule_based_risk_assessment(opp, context)


async def _gather_deal_context(db: AsyncSession, opp: Opportunity) -> dict:
    """Gather all relevant context for risk assessment."""
    now = datetime.now(timezone.utc)

    # Signals
    signals = (
        await db.execute(
            select(OpportunitySignal)
            .where(OpportunitySignal.opportunity_id == opp.id)
            .order_by(OpportunitySignal.created_at.desc())
            .limit(20)
        )
    ).scalars().all()

    negative_signal_count = sum(
        1 for s in signals if s.signal_type in ("pricing_concern", "competitor", "objection")
    )

    # Quotes
    quote_count = (
        await db.execute(
            select(func.count(Quote.id)).where(Quote.opportunity_id == opp.id)
        )
    ).scalar() or 0

    # Activities
    activity_count = 0
    if opp.customer_id:
        cutoff = now - timedelta(days=30)
        activity_count = (
            await db.execute(
                select(func.count(ActivityLog.id)).where(
                    ActivityLog.customer_id == opp.customer_id,
                    ActivityLog.created_at >= cutoff,
                )
            )
        ).scalar() or 0

    # Staleness
    updated = opp.updated_at
    if updated and updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    days_stale = (now - updated).days if updated else 0

    return {
        "signals": signals,
        "negative_signal_count": negative_signal_count,
        "quote_count": quote_count,
        "activity_count": activity_count,
        "days_stale": days_stale,
    }


async def _claude_risk_assessment(opp: Opportunity, context: dict) -> dict | None:
    """Use Claude for risk assessment with structured output."""
    try:
        signal_summary = ", ".join(
            f"{s.signal_type}({s.severity})" for s in context["signals"][:10]
        )

        prompt_parts = [
            f"Firsat: {opp.title}",
            f"Asama: {opp.stage}",
            f"Tutar: {opp.amount} {opp.currency}",
            f"Hareketsiz gun: {context['days_stale']}",
            f"Teklif sayisi: {context['quote_count']}",
            f"Son 30 gun aktivite: {context['activity_count']}",
            f"Sinyaller: {signal_summary or 'Yok'}",
            f"Olumsuz sinyal sayisi: {context['negative_signal_count']}",
        ]

        # RAG: add similar historical deals for context
        from app.services.vector_store import find_similar_deals, store_deal

        query = f"{opp.title} {opp.stage} {signal_summary}"
        similar_deals = await find_similar_deals(query, limit=5)
        if similar_deals:
            prompt_parts.append("\nBenzer Gecmis Firsatlar:")
            for deal in similar_deals:
                prompt_parts.append(
                    f"- {deal.get('title', '?')} "
                    f"(Asama: {deal.get('stage')}, "
                    f"Sonuc: {deal.get('outcome')}, "
                    f"Risk: {deal.get('risk_level')})"
                )

        prompt_parts.append(
            "\nBu firsatin risk seviyesini degerlendir. JSON formatinda cevap ver:\n"
            '{"risk_score": 0-100, "risk_level": "low|medium|high|critical", '
            '"factors": [{"name": "...", "impact": "high|medium|low", "evidence": "..."}], '
            '"recommendations": ["..."]}'
        )

        prompt = "\n".join(prompt_parts)

        response = await claude_messages_create(
            model=settings.AI_MODEL_NAME,
            max_tokens=512,
            system=(
                "Sen bir satis risk analiz asistanisin. Firsatlarin risk seviyesini "
                "degerlendir ve aciklanabilir faktorlerle sonuc don."
            ),
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text if response.content else None
        parsed = parse_claude_json(text)
        if parsed is not None:
            valid_levels = {"low", "medium", "high", "critical"}
            if parsed.get("risk_level") in valid_levels:
                result = {
                    "opportunity_id": opp.id,
                    "risk_score": min(100, max(0, int(parsed.get("risk_score", 50)))),
                    "risk_level": parsed["risk_level"],
                    "factors": parsed.get("factors", []),
                    "recommendations": parsed.get("recommendations", []),
                    "method": "ai",
                }

                # Store current deal for future RAG queries
                await store_deal({
                    "id": opp.id,
                    "title": opp.title,
                    "stage": opp.stage,
                    "amount": opp.amount,
                    "outcome": opp.status,
                    "risk_level": result.get("risk_level", "unknown"),
                    "customer_name": opp.customer.name if opp.customer else "",
                    "signal_summary": signal_summary,
                })

                return result
    except CircuitOpenError as exc:
        logger.warning("Claude breaker open; using rule-based fallback: %s", exc)
        return None
    except Exception as exc:
        logger.error("Claude risk assessment hatasi: %s", exc)

    return None


def _rule_based_risk_assessment(opp: Opportunity, context: dict) -> dict:
    """Rule-based deal risk scoring fallback."""
    risk_score = 0
    factors = []
    recommendations = []

    # Factor: No recent activity
    if context["activity_count"] == 0:
        risk_score += RISK_WEIGHTS["no_activity"]
        factors.append({
            "name": "Aktivite eksikligi",
            "impact": "high",
            "evidence": "Son 30 gunde musteri ile hicbir aktivite yok",
        })
        recommendations.append("Musteri ile iletisime gecin veya toplanti planlayin.")

    # Factor: Negative signals
    if context["negative_signal_count"] > 0:
        impact = "high" if context["negative_signal_count"] >= 3 else "medium"
        score_add = min(RISK_WEIGHTS["negative_signals"], context["negative_signal_count"] * 7)
        risk_score += score_add
        factors.append({
            "name": "Olumsuz sinyaller",
            "impact": impact,
            "evidence": f"{context['negative_signal_count']} olumsuz sinyal tespit edildi",
        })
        recommendations.append("Olumsuz sinyalleri inceleyin ve aksiyon alin.")

    # Factor: No quotes
    if context["quote_count"] == 0 and opp.stage not in ("prospecting",):
        risk_score += RISK_WEIGHTS["no_quotes"]
        factors.append({
            "name": "Teklif eksikligi",
            "impact": "medium",
            "evidence": f"Asama '{opp.stage}' ama henuz teklif olusturulmamis",
        })
        recommendations.append("Musteri icin teklif hazirlayip gonderin.")

    # Factor: Stale deal
    if context["days_stale"] > 14:
        impact = "high" if context["days_stale"] > 30 else "medium"
        risk_score += RISK_WEIGHTS["stale_deal"]
        factors.append({
            "name": "Hareketsiz firsat",
            "impact": impact,
            "evidence": f"{context['days_stale']} gundur guncelleme yapilmamis",
        })
        recommendations.append("Firsati guncelleyin veya kapatmayi degerlendirin.")

    # Factor: Low deal health score
    deal_health = getattr(opp, "deal_health_score", None)
    if deal_health is not None and deal_health < 40:
        risk_score += RISK_WEIGHTS["low_health_score"]
        factors.append({
            "name": "Dusuk saglik skoru",
            "impact": "high",
            "evidence": f"Firsat saglik skoru: {deal_health}/100",
        })

    risk_score = min(100, risk_score)

    if risk_score >= 70:
        risk_level = "critical"
    elif risk_score >= 50:
        risk_level = "high"
    elif risk_score >= 30:
        risk_level = "medium"
    else:
        risk_level = "low"

    return {
        "opportunity_id": opp.id,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "factors": factors,
        "recommendations": recommendations,
        "method": "rule_based",
    }


async def predict_close_probability(db: AsyncSession, opportunity_id: int) -> dict:
    """Predict close probability for an opportunity using Claude AI or rule-based fallback.

    Returns {close_probability, confidence, factors, next_steps}.
    """
    # Sprint 5: prefer heuristic predictive scoring service (explainable & calibratable).
    # Keep Claude as an optional enhancement, but always provide a deterministic baseline.
    from app.services.predictive_scoring_service import predict_close_probability as heuristic_predict

    stmt = (
        select(Opportunity)
        .options(
            selectinload(Opportunity.owner),
            selectinload(Opportunity.customer),
        )
        .where(Opportunity.id == opportunity_id)
    )
    result = await db.execute(stmt)
    opp = result.scalar_one_or_none()

    if not opp:
        return {"error": "Firsat bulunamadi"}

    heuristic = await heuristic_predict(db, opportunity_id)
    if "error" in heuristic:
        return heuristic

    now = datetime.now(timezone.utc)

    # Gather context
    context = await _gather_deal_context(db, opp)

    # Deal health score
    deal_health = getattr(opp, "deal_health_score", None) or 50

    # Days since created
    created_at = opp.created_at
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    days_since_created = (now - created_at).days if created_at else 0

    # Days to close_date
    days_to_close = None
    if opp.close_date:
        close_dt = opp.close_date
        if hasattr(close_dt, "tzinfo") and close_dt.tzinfo is None:
            close_dt = close_dt.replace(tzinfo=timezone.utc)
        if hasattr(close_dt, "date"):
            days_to_close = (close_dt - now).days
        else:
            from datetime import date as date_type

            if isinstance(close_dt, date_type):
                days_to_close = (close_dt - now.date()).days

    prediction_context = {
        "stage_probability_pct": int(round(float(getattr(opp, "probability", 0.25)) * 100)),
        "signals_count": len(context["signals"]),
        "negative_signal_count": context["negative_signal_count"],
        "activity_count": context["activity_count"],
        "quote_count": context["quote_count"],
        "deal_health_score": deal_health,
        "days_since_created": days_since_created,
        "days_to_close": days_to_close,
        "days_stale": context["days_stale"],
    }

    # Strategy 1: Claude AI prediction
    if settings.ANTHROPIC_API_KEY:
        ai_result = await _claude_close_prediction(opp, prediction_context)
        if ai_result:
            # Merge: keep AI output, but also return heuristic fields for UI explainability consistency.
            ai_result.setdefault("confidence_band", ai_result.get("confidence"))
            ai_result.setdefault("close_probability_pct", ai_result.get("close_probability"))
            return {
                **heuristic,
                **ai_result,
                "method": "ai+heuristic_v1",
            }

    # Strategy 2: heuristic-only
    return heuristic


async def _claude_close_prediction(opp: Opportunity, context: dict) -> dict | None:
    """Use Claude for close probability prediction."""
    try:
        owner_name = opp.owner.full_name if opp.owner else "Bilinmiyor"
        customer_name = opp.customer.name if opp.customer else "Bilinmiyor"

        prompt = (
            f"Firsat: {opp.title}\n"
            f"Asama: {opp.stage}\n"
            f"Tutar: {opp.amount} {opp.currency}\n"
            f"Musteri: {customer_name}\n"
            f"Sahip: {owner_name}\n"
            f"Sinyal sayisi: {context['signals_count']} (olumsuz: {context['negative_signal_count']})\n"
            f"Aktivite sayisi (30 gun): {context['activity_count']}\n"
            f"Teklif sayisi: {context['quote_count']}\n"
            f"Saglik skoru: {context['deal_health_score']}\n"
            f"Olusturulma: {context['days_since_created']} gun once\n"
            f"Kapanisa kalan: {context['days_to_close']} gun\n"
            f"Hareketsiz: {context['days_stale']} gun\n\n"
            "Bu firsatin kapanma olasiligini degerlendir. JSON formatinda cevap ver:\n"
            '{"close_probability": 0-100, "confidence": "high|medium|low", '
            '"factors": [{"name": "...", "impact": "positive|negative|neutral", "evidence": "..."}], '
            '"next_steps": ["..."]}'
        )

        response = await claude_messages_create(
            model=settings.AI_MODEL_NAME,
            max_tokens=512,
            system=(
                "Sen bir satis tahmin asistanisin. Firsatlarin kapanma olasiligini "
                "degerlendir ve aciklanabilir faktorlerle sonuc don."
            ),
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text if response.content else None
        parsed = parse_claude_json(text)
        if parsed is not None:
            valid_confidence = {"high", "medium", "low"}
            if parsed.get("confidence") in valid_confidence:
                return {
                    "opportunity_id": opp.id,
                    "close_probability": min(100, max(0, int(parsed.get("close_probability", 50)))),
                    "confidence": parsed["confidence"],
                    "factors": parsed.get("factors", []),
                    "next_steps": parsed.get("next_steps", []),
                    "method": "ai",
                }
    except CircuitOpenError as exc:
        logger.warning("Claude breaker open; using rule-based fallback: %s", exc)
        return None
    except Exception as exc:
        logger.error("Claude close prediction hatasi: %s", exc)

    return None


def _rule_based_close_prediction(opp: Opportunity, context: dict) -> dict:
    """Rule-based close probability prediction fallback."""
    # Single source of truth: stage probability service (pct).
    base_probability = int(context.get("stage_probability_pct") or 0)
    if base_probability <= 0:
        # best-effort: sync call to async getter not possible here; keep safe default
        base_probability = 25
    factors = []
    next_steps = []

    # Modifier: has quotes
    if context["quote_count"] > 0:
        base_probability += 10
        factors.append({
            "name": "Teklif mevcut",
            "impact": "positive",
            "evidence": f"{context['quote_count']} teklif olusturulmus",
        })
    else:
        factors.append({
            "name": "Teklif yok",
            "impact": "negative",
            "evidence": "Henuz teklif olusturulmamis",
        })
        next_steps.append("Musteri icin teklif hazirlayip gonderin.")

    # Modifier: negative signals
    if context["negative_signal_count"] > 0:
        penalty = context["negative_signal_count"] * 5
        base_probability -= penalty
        factors.append({
            "name": "Olumsuz sinyaller",
            "impact": "negative",
            "evidence": f"{context['negative_signal_count']} olumsuz sinyal tespit edildi",
        })
        next_steps.append("Olumsuz sinyalleri inceleyin ve cozum uretin.")

    # Modifier: recent activity
    if context["activity_count"] > 0:
        base_probability += 10
        factors.append({
            "name": "Aktif iletisim",
            "impact": "positive",
            "evidence": f"Son 30 gunde {context['activity_count']} aktivite",
        })
    else:
        factors.append({
            "name": "Aktivite eksikligi",
            "impact": "negative",
            "evidence": "Son 30 gunde hicbir aktivite yok",
        })
        next_steps.append("Musteri ile iletisime gecin veya toplanti planlayin.")

    # Modifier: staleness
    if context["days_stale"] > 14:
        base_probability -= 10
        factors.append({
            "name": "Hareketsiz firsat",
            "impact": "negative",
            "evidence": f"{context['days_stale']} gundur guncelleme yapilmamis",
        })
        next_steps.append("Firsati guncelleyin veya durumunu degerlendirin.")

    # Modifier: health score
    if context["deal_health_score"] < 40:
        base_probability -= 10
        factors.append({
            "name": "Dusuk saglik skoru",
            "impact": "negative",
            "evidence": f"Saglik skoru: {context['deal_health_score']}/100",
        })

    close_probability = max(0, min(100, base_probability))

    # Determine confidence
    if context["activity_count"] > 3 and context["quote_count"] > 0:
        confidence = "high"
    elif context["activity_count"] > 0 or context["quote_count"] > 0:
        confidence = "medium"
    else:
        confidence = "low"

    if not next_steps:
        next_steps.append("Mevcut durumu koruyun ve ilerlemeyi takip edin.")

    return {
        "opportunity_id": opp.id,
        "close_probability": close_probability,
        "confidence": confidence,
        "factors": factors,
        "next_steps": next_steps,
        "method": "rule_based",
    }
