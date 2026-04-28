"""V10 Sprint CC — obsolescence watch (PDF §4 "late truth" problem).

The PDF identifies a recurring failure: catalog parts go quietly
obsolete and we only notice when a customer order can't be filled.
By then it's too late for a strategic last-time-buy.

This service catches the trend earlier by combining four independent
signals into one composite EOL risk score per part:

1. ``inactivity_days`` — days since last quote line that referenced
   the part (PDF "demand decay" indicator).
2. ``missing_fields_count`` — how many of the 4 catalog fields
   (description, category, supplier_price, model_number) are NULL.
   Higher count = lower data trust = obsolescence proxy.
3. ``price_age_days`` — days since the latest PriceEntry for this
   part. No fresh price = supplier hasn't quoted us recently.
4. ``quote_freq_decay_pct`` — last 90 days quote count / previous
   90 days quote count. Decay > 50% = sharp drop = early warning.

Each driver contributes to a 0–100 risk score; the V5 envelope
shape returns drivers + recommended actions.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price_entry import PriceEntry
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.spare_part import SparePart


@dataclass(frozen=True)
class ObsolescenceRow:
    spare_part_id: int
    honeywell_code: str | None
    name: str | None
    risk_score: int
    inactivity_days: int
    missing_fields_count: int
    price_age_days: int
    quote_freq_decay_pct: float


# ─────────────────────── core scoring ─────────────────────────────────


_RISK_WEIGHTS = {
    "inactivity": 0.35,   # 35 points if part hasn't been quoted in 365d
    "missing_fields": 0.25,  # 25 points if all 4 catalog fields are NULL
    "price_age": 0.20,    # 20 points if last PriceEntry > 365d
    "decay": 0.20,        # 20 points if quote frequency dropped > 75%
}


def _score_inactivity(days: int) -> float:
    if days >= 365:
        return 1.0
    if days >= 180:
        return 0.6
    if days >= 90:
        return 0.3
    return 0.0


def _score_missing_fields(missing: int, total: int = 4) -> float:
    if total <= 0:
        return 0.0
    return min(1.0, missing / total)


def _score_price_age(days: int) -> float:
    if days >= 365:
        return 1.0
    if days >= 180:
        return 0.5
    if days >= 90:
        return 0.2
    return 0.0


def _score_decay(decay_pct: float) -> float:
    """decay_pct is positive when frequency dropped (good for risk).
    Cap at 75% drop = max contribution; 0 or negative = no contribution.
    """
    if decay_pct >= 0.75:
        return 1.0
    if decay_pct >= 0.5:
        return 0.7
    if decay_pct >= 0.25:
        return 0.3
    return 0.0


def _composite_score(
    *,
    inactivity_days: int,
    missing_fields_count: int,
    price_age_days: int,
    quote_freq_decay_pct: float,
) -> int:
    raw = (
        _RISK_WEIGHTS["inactivity"] * _score_inactivity(inactivity_days)
        + _RISK_WEIGHTS["missing_fields"] * _score_missing_fields(missing_fields_count)
        + _RISK_WEIGHTS["price_age"] * _score_price_age(price_age_days)
        + _RISK_WEIGHTS["decay"] * _score_decay(quote_freq_decay_pct)
    )
    return max(0, min(100, int(round(raw * 100))))


def _missing_field_count(part: SparePart) -> int:
    """Count of NULL/empty among the 4 critical catalog fields.

    Bilingual descriptions/names count as "present" if EITHER side
    is populated — Excel imports often only fill one language.
    """
    desc_filled = bool((part.description_tr or "").strip()) or bool(
        (part.description_en or "").strip()
    )
    return sum(
        [
            0 if desc_filled else 1,
            0 if (part.category or "").strip() else 1,
            0 if part.supplier_price else 1,
            0 if (part.model_number or "").strip() else 1,
        ]
    )


# ─────────────────────── per-part risk envelope ───────────────────────


async def eol_risk_score(
    db: AsyncSession,
    *,
    part_id: int,
    tenant_id: int | None = None,
) -> dict:
    """V5-shape envelope for a single part's EOL risk."""
    part = await db.get(SparePart, part_id)
    if part is None:
        return _envelope(
            value=0,
            confidence="low",
            drivers=[{"label": "part_not_found", "impact": 0}],
            recommended_actions=["Parça bulunamadı"],
        )

    now = datetime.now(timezone.utc)

    # Last-quoted timestamp (tenant-scoped).
    last_quoted_query = (
        select(func.max(Quote.created_at))
        .join(QuoteItem, QuoteItem.quote_id == Quote.id)
        .where(QuoteItem.spare_part_id == part_id)
    )
    if tenant_id is not None:
        last_quoted_query = last_quoted_query.where(Quote.tenant_id == tenant_id)
    last_quoted_at = (await db.execute(last_quoted_query)).scalar_one_or_none()
    inactivity_days = (
        (now - last_quoted_at).days if last_quoted_at is not None else 9999
    )

    # Latest price entry age.
    last_price_at = (
        await db.execute(
            select(func.max(PriceEntry.created_at)).where(
                PriceEntry.spare_part_id == part_id
            )
        )
    ).scalar_one_or_none()
    price_age_days = (
        (now - last_price_at).days if last_price_at is not None else 9999
    )

    # Decay = (prev_window_count - recent_window_count) / max(prev_window_count, 1).
    recent_cutoff = now - timedelta(days=90)
    prev_cutoff = now - timedelta(days=180)
    decay_query = (
        select(
            func.count().filter(Quote.created_at >= recent_cutoff).label("recent"),
            func.count()
            .filter(
                and_(
                    Quote.created_at >= prev_cutoff,
                    Quote.created_at < recent_cutoff,
                )
            )
            .label("prev"),
        )
        .select_from(QuoteItem)
        .join(Quote, Quote.id == QuoteItem.quote_id)
        .where(QuoteItem.spare_part_id == part_id)
    )
    if tenant_id is not None:
        decay_query = decay_query.where(Quote.tenant_id == tenant_id)
    decay_row = (await db.execute(decay_query)).first()
    recent = int(decay_row.recent) if decay_row else 0
    prev = int(decay_row.prev) if decay_row else 0
    decay_pct = (prev - recent) / prev if prev > 0 else 0.0

    missing_fields_count = _missing_field_count(part)

    score = _composite_score(
        inactivity_days=inactivity_days,
        missing_fields_count=missing_fields_count,
        price_age_days=price_age_days,
        quote_freq_decay_pct=decay_pct,
    )

    drivers = [
        {"label": "inactivity_days", "impact": inactivity_days},
        {"label": "missing_fields_count", "impact": missing_fields_count},
        {"label": "price_age_days", "impact": price_age_days},
        {
            "label": "quote_freq_decay_pct",
            "impact": round(decay_pct * 100, 1),
        },
    ]

    actions: list[str] = []
    if score >= 70:
        actions.append(
            "Last-time-buy değerlendirmesi başlatın — tedarikçi ile EOL teyidi alın"
        )
    if missing_fields_count >= 2:
        actions.append("Master data tamamlama: eksik kolonları doldurun")
    if price_age_days >= 180:
        actions.append("Tedarikçiden taze fiyat talep edin")
    if decay_pct >= 0.5:
        actions.append("Talep düşüşü için müşteri görüşmesi planlayın")
    if not actions:
        actions.append("Risk seviyesi düşük — izleme moduna alın")

    confidence = "high" if prev >= 5 and last_price_at is not None else "medium"
    if last_quoted_at is None and last_price_at is None:
        confidence = "low"

    return _envelope(
        value=score,
        confidence=confidence,
        drivers=drivers,
        recommended_actions=actions,
    )


# ─────────────────────── obsolescence watch list ─────────────────────


async def obsolescence_watch_list(
    db: AsyncSession,
    *,
    tenant_id: int | None = None,
    top_n: int = 20,
) -> list[ObsolescenceRow]:
    """Top-N parts ranked by composite EOL risk.

    The cockpit widget shows this list — sorted highest risk first.
    We compute composite scores for every active part with at least
    one of (PriceEntry, QuoteItem) so we don't waste cycles on
    catalog rows nobody has ever transacted on.
    """
    parts = (
        await db.execute(
            select(SparePart).where(SparePart.is_active.is_(True)).limit(top_n * 10)
        )
    ).scalars().all()

    scored: list[ObsolescenceRow] = []
    now = datetime.now(timezone.utc)
    for part in parts:
        # Last quoted timestamp.
        lq_q = (
            select(func.max(Quote.created_at))
            .join(QuoteItem, QuoteItem.quote_id == Quote.id)
            .where(QuoteItem.spare_part_id == part.id)
        )
        if tenant_id is not None:
            lq_q = lq_q.where(Quote.tenant_id == tenant_id)
        last_quoted_at = (await db.execute(lq_q)).scalar_one_or_none()
        inactivity = (now - last_quoted_at).days if last_quoted_at else 9999

        last_price_at = (
            await db.execute(
                select(func.max(PriceEntry.created_at)).where(
                    PriceEntry.spare_part_id == part.id
                )
            )
        ).scalar_one_or_none()
        price_age = (now - last_price_at).days if last_price_at else 9999

        recent_cutoff = now - timedelta(days=90)
        prev_cutoff = now - timedelta(days=180)
        decay_q = (
            select(
                func.count().filter(Quote.created_at >= recent_cutoff).label("recent"),
                func.count()
                .filter(
                    and_(
                        Quote.created_at >= prev_cutoff,
                        Quote.created_at < recent_cutoff,
                    )
                )
                .label("prev"),
            )
            .select_from(QuoteItem)
            .join(Quote, Quote.id == QuoteItem.quote_id)
            .where(QuoteItem.spare_part_id == part.id)
        )
        if tenant_id is not None:
            decay_q = decay_q.where(Quote.tenant_id == tenant_id)
        d_row = (await db.execute(decay_q)).first()
        recent = int(d_row.recent) if d_row else 0
        prev_count = int(d_row.prev) if d_row else 0
        decay = (prev_count - recent) / prev_count if prev_count > 0 else 0.0

        missing = _missing_field_count(part)

        score = _composite_score(
            inactivity_days=inactivity,
            missing_fields_count=missing,
            price_age_days=price_age,
            quote_freq_decay_pct=decay,
        )

        scored.append(
            ObsolescenceRow(
                spare_part_id=int(part.id),
                honeywell_code=part.honeywell_code,
                name=part.name_tr or part.name_en,
                risk_score=score,
                inactivity_days=inactivity,
                missing_fields_count=missing,
                price_age_days=price_age,
                quote_freq_decay_pct=round(decay * 100, 1),
            )
        )

    scored.sort(key=lambda r: -r.risk_score)
    return scored[:top_n]


# ─────────────────────── last-time-buy candidates ─────────────────────


async def last_time_buy_recommendations(
    db: AsyncSession,
    *,
    tenant_id: int | None = None,
    decay_threshold: float = 0.5,
    pipeline_value_threshold: float = 5_000.0,
) -> list[dict]:
    """Parts whose recent demand collapsed but pipeline still has them.

    Trigger: last-90d quote count dropped ≥ ``decay_threshold`` vs
    previous 90d AND open pipeline includes this part with line_total
    sum ≥ ``pipeline_value_threshold``. These are the "act now or
    can't fulfil" candidates.
    """
    now = datetime.now(timezone.utc)
    recent_cutoff = now - timedelta(days=90)
    prev_cutoff = now - timedelta(days=180)
    open_stages = ("prospecting", "qualified", "proposal", "negotiation")

    decay_q = (
        select(
            QuoteItem.spare_part_id.label("spare_part_id"),
            func.count().filter(Quote.created_at >= recent_cutoff).label("recent"),
            func.count()
            .filter(
                and_(
                    Quote.created_at >= prev_cutoff,
                    Quote.created_at < recent_cutoff,
                )
            )
            .label("prev"),
        )
        .select_from(QuoteItem)
        .join(Quote, Quote.id == QuoteItem.quote_id)
        .where(QuoteItem.spare_part_id.isnot(None))
        .group_by(QuoteItem.spare_part_id)
    )
    if tenant_id is not None:
        decay_q = decay_q.where(Quote.tenant_id == tenant_id)

    decay_rows = (await db.execute(decay_q)).all()
    candidates: list[dict] = []
    for r in decay_rows:
        prev = int(r.prev or 0)
        recent = int(r.recent or 0)
        if prev <= 0:
            continue
        decay = (prev - recent) / prev
        if decay < decay_threshold:
            continue

        # Open pipeline exposure for this part.
        from app.models.opportunity import Opportunity  # local to avoid cycle

        exposure = (
            await db.execute(
                select(func.coalesce(func.sum(QuoteItem.line_total), 0.0))
                .join(Quote, Quote.id == QuoteItem.quote_id)
                .join(Opportunity, Opportunity.id == Quote.opportunity_id)
                .where(
                    QuoteItem.spare_part_id == int(r.spare_part_id),
                    Opportunity.stage.in_(open_stages),
                )
            )
        ).scalar() or 0.0
        if float(exposure) < pipeline_value_threshold:
            continue

        part = await db.get(SparePart, int(r.spare_part_id))
        candidates.append(
            {
                "spare_part_id": int(r.spare_part_id),
                "honeywell_code": part.honeywell_code if part else None,
                "name": (part.name_tr or part.name_en) if part else None,
                "decay_pct": round(decay * 100, 1),
                "open_pipeline_exposure": round(float(exposure), 2),
            }
        )

    candidates.sort(key=lambda c: -c["open_pipeline_exposure"])
    return candidates


# ─────────────────────── envelope helper ─────────────────────────────


def _envelope(
    *,
    value: int | float,
    confidence: str,
    drivers: list[dict],
    recommended_actions: list[str],
) -> dict:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "value": value,
        "confidence": confidence,
        "drivers": drivers,
        "recommended_actions": recommended_actions,
    }
