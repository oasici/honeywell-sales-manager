"""V10 Sprint BB — pricing intelligence over PriceEntry history.

Three derivations that catch real revenue leaks:

- ``inflation_tax_summary`` — what the last 12 months of price drift
  costs us when projected onto the open pipeline (PDF §1).
- ``stale_pricing_alerts`` — parts whose latest PriceEntry is past
  ``valid_until`` or older than ``max_age_days`` (PDF §2).
- ``margin_health_alerts`` — parts where the derived margin from
  the latest PriceEntry slipped below 80% of the SparePart's
  ``min_margin_pct`` floor (PDF §3).

Every output uses the V5 envelope shape — ``value``, ``confidence``,
``drivers``, ``recommended_actions`` — so the cockpit panels reuse
existing render components without bespoke formatting.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity
from app.models.price_entry import PriceEntry
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.spare_part import SparePart


@dataclass(frozen=True)
class StalePricingRow:
    spare_part_id: int
    honeywell_code: str | None
    name: str | None
    last_price_at: datetime | None
    valid_until: date | None
    age_days: int
    reason: str  # "expired_valid_until" | "stale_created_at" | "no_price_entry"


@dataclass(frozen=True)
class MarginAlertRow:
    spare_part_id: int
    honeywell_code: str | None
    name: str | None
    derived_margin_pct: float
    min_margin_pct: float
    severity: str  # "warning" | "danger"


# ─────────────────────── inflation tax ───────────────────────────────


async def inflation_tax_summary(
    db: AsyncSession,
    *,
    tenant_id: int | None = None,
    months: int = 12,
) -> dict:
    """V5-envelope summary of price drift × open pipeline exposure.

    Algorithm:
    1. For each part with ≥ 2 PriceEntries, compute
       ``(latest.list_price / oldest_in_window.list_price) - 1`` =
       drift_pct. Use *list_price* (catalog) rather than *net_price*
       so customer-specific discounts don't pollute the signal.
    2. Compute the open-pipeline exposure: sum of QuoteItem.line_total
       where the parent Quote is on an opportunity in an open stage.
    3. Multiply per-part drift × per-part exposure → "inflation tax"
       per part, summed = total exposure.

    The ``confidence`` is "low" when fewer than 5 parts contribute,
    "high" when ≥ 50, "medium" otherwise.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)

    # Per-part oldest-in-window + latest list_price.
    oldest_subq = (
        select(
            PriceEntry.spare_part_id.label("spare_part_id"),
            func.min(PriceEntry.created_at).label("oldest_at"),
            func.max(PriceEntry.created_at).label("latest_at"),
        )
        .where(PriceEntry.created_at >= cutoff)
        .group_by(PriceEntry.spare_part_id)
        .subquery()
    )

    # Pull anchor + tip prices for every contributing part.
    rows = (
        await db.execute(
            select(
                oldest_subq.c.spare_part_id,
                oldest_subq.c.oldest_at,
                oldest_subq.c.latest_at,
            )
        )
    ).all()
    if not rows:
        return _envelope(
            value=0.0,
            confidence="low",
            drivers=[{"label": "no_price_history", "impact": 0}],
            recommended_actions=[
                "Fiyat geçmişi kayıtsız — PriceEntry akışını gözden geçirin"
            ],
        )

    drift_per_part: dict[int, float] = {}
    for r in rows:
        pid = int(r.spare_part_id)
        oldest = (
            await db.execute(
                select(PriceEntry.list_price)
                .where(
                    PriceEntry.spare_part_id == pid,
                    PriceEntry.created_at == r.oldest_at,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        latest = (
            await db.execute(
                select(PriceEntry.list_price)
                .where(
                    PriceEntry.spare_part_id == pid,
                    PriceEntry.created_at == r.latest_at,
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if oldest and oldest > 0 and latest is not None:
            drift_per_part[pid] = (float(latest) / float(oldest)) - 1.0

    if not drift_per_part:
        return _envelope(
            value=0.0,
            confidence="low",
            drivers=[{"label": "single_entry_per_part", "impact": 0}],
            recommended_actions=[
                "Fiyat geçmişi yetersiz — 12 aylık 2'den fazla PriceEntry gerekli"
            ],
        )

    # Open-pipeline exposure per part.
    open_stages = ("prospecting", "qualified", "proposal", "negotiation")
    pipeline_filter = [
        QuoteItem.spare_part_id.in_(drift_per_part.keys()),
        Opportunity.stage.in_(open_stages),
    ]
    if tenant_id is not None:
        pipeline_filter.append(Opportunity.tenant_id == tenant_id)

    pipeline_rows = (
        await db.execute(
            select(
                QuoteItem.spare_part_id.label("spare_part_id"),
                func.coalesce(func.sum(QuoteItem.line_total), 0.0).label("exposure"),
            )
            .join(Quote, Quote.id == QuoteItem.quote_id)
            .join(Opportunity, Opportunity.id == Quote.opportunity_id)
            .where(and_(*pipeline_filter))
            .group_by(QuoteItem.spare_part_id)
        )
    ).all()
    exposure_per_part = {int(r.spare_part_id): float(r.exposure or 0.0) for r in pipeline_rows}

    inflation_tax_total = 0.0
    drivers: list[dict] = []
    for pid, drift in drift_per_part.items():
        exposure = exposure_per_part.get(pid, 0.0)
        contribution = round(drift * exposure, 2)
        inflation_tax_total += contribution
        if contribution > 0:
            drivers.append(
                {
                    "label": f"part_{pid}",
                    "impact": contribution,
                    "drift_pct": round(drift * 100, 2),
                    "exposure": round(exposure, 2),
                }
            )
    drivers.sort(key=lambda d: -float(d.get("impact", 0)))
    drivers = drivers[:10]

    contributors = len(drift_per_part)
    confidence = "high" if contributors >= 50 else "medium" if contributors >= 5 else "low"

    return _envelope(
        value=round(inflation_tax_total, 2),
        confidence=confidence,
        drivers=drivers,
        recommended_actions=_inflation_tax_recommendations(inflation_tax_total),
    )


def _inflation_tax_recommendations(total: float) -> list[str]:
    if total > 0:
        return [
            "Açık pipeline'da fiyat artışını yansıtacak teklif revizyonu planlayın",
            "Yüksek drift'li parçalar için stratejik müşteri görüşmesi açın",
        ]
    return ["Fiyat artışı henüz pipeline'a yansımamış — izleme moduna alın"]


# ─────────────────────── stale pricing ───────────────────────────────


async def stale_pricing_alerts(
    db: AsyncSession,
    *,
    max_age_days: int = 180,
    tenant_id: int | None = None,
    limit: int = 100,
) -> list[StalePricingRow]:
    """Parts whose pricing data smells stale.

    Three independent reasons (all surfaced via the ``reason`` field):
    - ``expired_valid_until`` — latest PriceEntry's ``valid_until`` is in the past
    - ``stale_created_at`` — latest PriceEntry was created > max_age_days ago
    - ``no_price_entry`` — active SparePart with no PriceEntry rows at all
    """
    today = datetime.now(timezone.utc).date()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    latest_pe_subq = (
        select(
            PriceEntry.spare_part_id.label("spare_part_id"),
            func.max(PriceEntry.created_at).label("latest_at"),
        )
        .group_by(PriceEntry.spare_part_id)
        .subquery()
    )

    stmt = (
        select(
            SparePart.id.label("spare_part_id"),
            SparePart.honeywell_code,
            func.coalesce(SparePart.name_tr, SparePart.name_en).label("name"),
            latest_pe_subq.c.latest_at,
            PriceEntry.valid_until,
        )
        .select_from(SparePart)
        .outerjoin(
            latest_pe_subq, latest_pe_subq.c.spare_part_id == SparePart.id
        )
        .outerjoin(
            PriceEntry,
            and_(
                PriceEntry.spare_part_id == SparePart.id,
                PriceEntry.created_at == latest_pe_subq.c.latest_at,
            ),
        )
        .where(SparePart.is_active.is_(True))
        .order_by(latest_pe_subq.c.latest_at.asc().nullsfirst())
        .limit(limit)
    )

    rows = (await db.execute(stmt)).all()
    out: list[StalePricingRow] = []
    for r in rows:
        latest_at = r.latest_at
        valid_until = r.valid_until
        if latest_at is None:
            reason = "no_price_entry"
            age_days = max_age_days
        elif valid_until is not None and valid_until < today:
            reason = "expired_valid_until"
            age_days = (today - valid_until).days
        elif latest_at < cutoff:
            reason = "stale_created_at"
            age_days = (datetime.now(timezone.utc) - latest_at).days
        else:
            # Latest entry is fresh and within validity → not stale.
            continue
        out.append(
            StalePricingRow(
                spare_part_id=int(r.spare_part_id),
                honeywell_code=r.honeywell_code,
                name=r.name,
                last_price_at=latest_at,
                valid_until=valid_until,
                age_days=int(age_days),
                reason=reason,
            )
        )
    return out


# ─────────────────────── margin health ───────────────────────────────


async def margin_health_alerts(
    db: AsyncSession,
    *,
    tenant_id: int | None = None,
    limit: int = 100,
) -> list[MarginAlertRow]:
    """Parts where the derived margin slipped below the floor.

    Derived margin: ``(net_price - transfer_price) / net_price`` from
    the latest PriceEntry. We tolerate missing ``transfer_price`` —
    parts without a transfer cost cannot have their margin computed
    so they're excluded (avoids false positives).

    Severity:
    - ``danger`` if derived margin < min_margin_pct × 0.5
    - ``warning`` if derived margin < min_margin_pct × 0.8 (the
      "approaching the floor" zone)
    """
    latest_pe_subq = (
        select(
            PriceEntry.spare_part_id.label("spare_part_id"),
            func.max(PriceEntry.created_at).label("latest_at"),
        )
        .group_by(PriceEntry.spare_part_id)
        .subquery()
    )

    stmt = (
        select(
            SparePart.id.label("spare_part_id"),
            SparePart.honeywell_code,
            func.coalesce(SparePart.name_tr, SparePart.name_en).label("name"),
            SparePart.transfer_price,
            SparePart.min_margin_pct,
            PriceEntry.net_price,
        )
        .join(latest_pe_subq, latest_pe_subq.c.spare_part_id == SparePart.id)
        .join(
            PriceEntry,
            and_(
                PriceEntry.spare_part_id == SparePart.id,
                PriceEntry.created_at == latest_pe_subq.c.latest_at,
            ),
        )
        .where(
            SparePart.is_active.is_(True),
            SparePart.transfer_price.isnot(None),
            SparePart.transfer_price > 0,
            SparePart.min_margin_pct > 0,
            PriceEntry.net_price > 0,
        )
        .limit(limit * 5)  # filter further in Python; cheap and clearer
    )

    rows = (await db.execute(stmt)).all()
    out: list[MarginAlertRow] = []
    for r in rows:
        net = float(r.net_price)
        transfer = float(r.transfer_price)
        if net <= 0:
            continue
        derived_margin = (net - transfer) / net
        floor = float(r.min_margin_pct) / 100.0
        warn_threshold = floor * 0.8
        danger_threshold = floor * 0.5
        if derived_margin >= warn_threshold:
            continue
        severity = "danger" if derived_margin < danger_threshold else "warning"
        out.append(
            MarginAlertRow(
                spare_part_id=int(r.spare_part_id),
                honeywell_code=r.honeywell_code,
                name=r.name,
                derived_margin_pct=round(derived_margin * 100, 2),
                min_margin_pct=round(float(r.min_margin_pct), 2),
                severity=severity,
            )
        )
    out.sort(key=lambda r: (r.severity != "danger", r.derived_margin_pct))
    return out[:limit]


# ─────────────────────── envelope helper ─────────────────────────────


def _envelope(
    *,
    value: float,
    confidence: str,
    drivers: list[dict],
    recommended_actions: list[str],
) -> dict:
    """V5-style envelope so the UI uses the same renderer as
    deal-health / churn-prediction / inflation-tax."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "value": value,
        "confidence": confidence,
        "drivers": drivers,
        "recommended_actions": recommended_actions,
    }
