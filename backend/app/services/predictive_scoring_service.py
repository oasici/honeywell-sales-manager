"""Predictive scoring (heuristic) — Sprint 5 MVP.

Goal: provide close_probability with explainable factors, not "mystery ML".
close_probability is returned as a float in [0, 1].
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.enums import OpportunitySignalType
from app.models.opportunity import Opportunity, OpportunitySignal
from app.models.quote import Quote
from app.services.stage_probability_service import get_stage_probability


@dataclass(frozen=True)
class CloseProbabilityFactor:
    key: str
    label: str
    impact: str  # positive | negative | neutral
    weight: float  # signed delta in probability points (e.g. +0.07)
    evidence: str | None = None


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _norm_linear(x: float, *, lo: float, hi: float) -> float:
    """Map x in [lo,hi] to [0,1] with clipping."""
    if hi <= lo:
        return 0.0
    return _clamp((x - lo) / (hi - lo), 0.0, 1.0)

def _norm_inverse_days(days: int | None, *, good_days: int, bad_days: int) -> float:
    """Return 1 when <=good_days, 0 when >=bad_days."""
    if days is None:
        return 0.0
    if bad_days <= good_days:
        return 0.0
    return 1.0 - _norm_linear(float(days), lo=float(good_days), hi=float(bad_days))

def _norm_count(count: int, *, good: int, excellent: int) -> float:
    """0..1 based on count thresholds."""
    if count <= 0:
        return 0.0
    if count >= excellent:
        return 1.0
    return _norm_linear(float(count), lo=float(good), hi=float(excellent))

def _severity_score(sev: str) -> float:
    return {"low": 0.33, "med": 0.66, "high": 1.0}.get(sev, 0.66)


async def _stage_base_probability(db: AsyncSession, stage: str) -> float:
    # Stage probabilities are centrally managed; reuse for baseline calibration.
    return await get_stage_probability(db, stage)


async def _activity_metrics(
    db: AsyncSession,
    *,
    opportunity_id: int,
    customer_id: int | None,
    now: datetime,
) -> tuple[int, int | None]:
    """Return (activity_count_30d, last_activity_days).

    Consistency rule:
    - Prefer opportunity-scoped activity logs (true deal timeline)
    - Fallback to customer-scoped activity logs (when older data wasn't linked)
    """
    cutoff = now - timedelta(days=30)

    # Prefer opportunity scoped
    activity_count_30d = (
        await db.execute(
            select(func.count(ActivityLog.id)).where(
                ActivityLog.opportunity_id == opportunity_id,
                ActivityLog.created_at >= cutoff,
            )
        )
    ).scalar() or 0

    last_activity = (
        await db.execute(
            select(func.max(ActivityLog.created_at)).where(
                ActivityLog.opportunity_id == opportunity_id
            )
        )
    ).scalar()

    # Fallback to customer scoped if no link exists yet
    if (activity_count_30d == 0 and last_activity is None) and customer_id:
        activity_count_30d = (
            await db.execute(
                select(func.count(ActivityLog.id)).where(
                    ActivityLog.customer_id == customer_id,
                    ActivityLog.created_at >= cutoff,
                )
            )
        ).scalar() or 0
        last_activity = (
            await db.execute(
                select(func.max(ActivityLog.created_at)).where(
                    ActivityLog.customer_id == customer_id
                )
            )
        ).scalar()

    last_activity_days = None
    if last_activity:
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        last_activity_days = (now - last_activity).days

    return int(activity_count_30d), last_activity_days


async def predict_close_probability(db: AsyncSession, opportunity_id: int) -> dict:
    """Return {close_probability, confidence_band, factors[], next_steps[]}."""
    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if not opp:
        return {"error": "Firsat bulunamadi"}

    now = datetime.now(timezone.utc)

    created_at = opp.created_at
    if created_at and created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    deal_age_days = (now - created_at).days if created_at else 0

    activity_count_30d, last_activity_days = await _activity_metrics(
        db,
        opportunity_id=opp.id,
        customer_id=opp.customer_id,
        now=now,
    )

    # Signals
    signals = (
        await db.execute(
            select(OpportunitySignal)
            .where(OpportunitySignal.opportunity_id == opp.id)
            .order_by(OpportunitySignal.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    negative_signals = [
        s
        for s in signals
        if s.signal_type
        in (
            OpportunitySignalType.PRICING_CONCERN.value,
            OpportunitySignalType.COMPETITOR.value,
            OpportunitySignalType.OBJECTION.value,
            OpportunitySignalType.DISCOUNT_RISK.value,
            OpportunitySignalType.SLA_BREACH.value,
            OpportunitySignalType.NO_TOUCH.value,
        )
        and not getattr(s, "is_resolved", False)
    ]
    positive_signals = [
        s
        for s in signals
        if s.signal_type == OpportunitySignalType.POSITIVE.value
        and not getattr(s, "is_resolved", False)
    ]

    # Quotes / discount ratio (use latest non-expired quote)
    quote_stmt = (
        select(Quote)
        .where(Quote.opportunity_id == opp.id)
        .order_by(Quote.created_at.desc())
        .limit(1)
    )
    latest_quote = (await db.execute(quote_stmt)).scalars().first()
    quote_count = (
        await db.execute(select(func.count(Quote.id)).where(Quote.opportunity_id == opp.id))
    ).scalar() or 0

    discount_ratio = None
    if latest_quote:
        denom = float(latest_quote.subtotal or 0.0)
        disc = float(latest_quote.discount_total or 0.0)
        discount_ratio = (disc / denom) if denom > 0 else (0.0 if disc == 0 else None)

    # Start with stage base.
    p = await _stage_base_probability(db, opp.stage)
    factors: list[CloseProbabilityFactor] = []
    next_steps: list[str] = []

    factors.append(
        CloseProbabilityFactor(
            key="stage_base",
            label=f"Asama baz olasiligi: {opp.stage}",
            impact="neutral",
            weight=0.0,
            evidence=f"base={round(p*100)}%",
        )
    )

    # v1.5 normalized features
    n_activity = _norm_count(int(activity_count_30d), good=1, excellent=5)  # 0..1
    n_recency = _norm_inverse_days(last_activity_days, good_days=3, bad_days=21)  # 0..1
    n_quotes = _norm_count(int(quote_count), good=1, excellent=3)  # 0..1
    n_discount = 0.0
    if discount_ratio is not None:
        # 0 at 0%, 1 at 25%+ (penalty)
        n_discount = _norm_linear(float(discount_ratio), lo=0.05, hi=0.25)

    neg_density = 0.0
    if negative_signals:
        sev_sum = sum(_severity_score(s.severity) for s in negative_signals[:5])
        neg_density = _clamp(sev_sum / 3.0, 0.0, 1.0)  # normalize roughly

    pos_density = _clamp(len(positive_signals) / 3.0, 0.0, 1.0)

    # Engagement: combine volume + recency
    engagement_score = _clamp(0.55 * n_activity + 0.45 * n_recency, 0.0, 1.0)
    engagement_delta = (engagement_score - 0.5) * 0.16  # [-0.08, +0.08]
    p += engagement_delta
    factors.append(
        CloseProbabilityFactor(
            key="engagement",
            label="Musteri etkilesimi",
            impact="positive" if engagement_delta >= 0 else "negative",
            weight=round(engagement_delta, 4),
            evidence=f"aktivite_30g={activity_count_30d}, son_aktivite_gun={last_activity_days}",
        )
    )
    if engagement_score < 0.35:
        next_steps.append("Musteri ile takip gorusmesi planlayin.")

    # Recency-specific penalty (extra push when really stale)
    if last_activity_days is not None and last_activity_days > 10:
        stale_penalty = -0.10 * _norm_linear(float(last_activity_days), lo=10.0, hi=30.0)
        p += stale_penalty
        factors.append(
            CloseProbabilityFactor(
                key="staleness",
                label="Hareketsizlik",
                impact="negative",
                weight=round(stale_penalty, 4),
                evidence=f"{last_activity_days} gundur aktivite yok",
            )
        )
        if last_activity_days > 14:
            next_steps.append("Firsati guncelleyin veya musteriyle temas kurun.")

    # Quotes: normalized influence
    quote_delta = (n_quotes - 0.4) * 0.12  # [-0.048, +0.072]
    p += quote_delta
    factors.append(
        CloseProbabilityFactor(
            key="quote_progress",
            label="Teklif varligi",
            impact="positive" if quote_delta >= 0 else "negative",
            weight=round(quote_delta, 4),
            evidence=f"teklif_sayisi={quote_count}",
        )
    )
    if quote_count == 0:
        next_steps.append("Teklif olusturup gonderin (en azindan taslak).")

    # Discount: normalized penalty
    if discount_ratio is not None:
        discount_penalty = -0.10 * n_discount  # up to -0.10
        p += discount_penalty
        factors.append(
            CloseProbabilityFactor(
                key="discount_pressure",
                label="Indirim baskisi",
                impact="negative" if discount_penalty < 0 else "neutral",
                weight=round(discount_penalty, 4),
                evidence=f"indirim_orani={round(discount_ratio*100)}%",
            )
        )
        if discount_ratio >= 0.20:
            next_steps.append("Indirim icin manager onayi/alternatif paket onerisi hazirlayin.")

    # Signals: normalized density
    if negative_signals:
        penalty = -0.18 * neg_density
        p += penalty
        factors.append(
            CloseProbabilityFactor(
                key="risk_signals",
                label="Risk sinyalleri",
                impact="negative",
                weight=round(penalty, 4),
                evidence=", ".join(f"{s.signal_type}({s.severity})" for s in negative_signals[:5]),
            )
        )
        next_steps.append("Sinyal detaylarini inceleyip itiraz/rekabet/pricing konularini ele alin.")

    if positive_signals:
        bonus = 0.10 * pos_density
        p += bonus
        factors.append(
            CloseProbabilityFactor(
                key="positive_signals",
                label="Olumlu sinyaller",
                impact="positive",
                weight=round(bonus, 4),
                evidence=", ".join(s.signal_type for s in positive_signals[:5]),
            )
        )

    # Deal age — very old deals without momentum tend to drift (normalized)
    if deal_age_days > 30:
        age_norm = _norm_linear(float(deal_age_days), lo=30.0, hi=120.0)
        momentum = _clamp(0.6 * engagement_score + 0.4 * n_quotes, 0.0, 1.0)
        age_penalty = -0.08 * age_norm * (1.0 - momentum)
        p += age_penalty
        factors.append(
            CloseProbabilityFactor(
                key="age_old",
                label="Eski firsat (momentum dusuk)",
                impact="negative",
                weight=round(age_penalty, 4),
                evidence=f"yas={deal_age_days} gun",
            )
        )

    close_probability = _clamp01(p)

    # Confidence band (data completeness + density)
    if quote_count > 0 and engagement_score >= 0.45 and (len(signals) >= 2):
        confidence_band = "high"
    elif quote_count > 0 or engagement_score >= 0.25:
        confidence_band = "medium"
    else:
        confidence_band = "low"

    # Sort factors by absolute weight (largest impact first), keep stage base first if present.
    stage_base = [f for f in factors if f.key == "stage_base"]
    rest = [f for f in factors if f.key != "stage_base"]
    rest.sort(key=lambda f: abs(f.weight), reverse=True)
    ordered = stage_base + rest

    return {
        "opportunity_id": opp.id,
        "close_probability": close_probability,
        "confidence_band": confidence_band,
        "factors": [
            {
                "key": f.key,
                "label": f.label,
                "name": f.label,  # backward-compatible for existing UI
                "impact": f.impact,
                "weight": round(f.weight, 4),
                "evidence": f.evidence,
            }
            for f in ordered
        ],
        "next_steps": next_steps[:6],
        "method": "heuristic_v1_5",
        # Backward-compat helpers (older UI used 0-100 + confidence):
        "close_probability_pct": int(round(close_probability * 100)),
        "confidence": confidence_band,
    }

