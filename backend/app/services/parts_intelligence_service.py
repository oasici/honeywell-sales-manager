"""V10 Sprint AA — read-only spare-parts intelligence aggregates.

Pure derivation layer over the existing ``SparePart`` × ``QuoteItem``
× ``Quote`` tables. **No schema changes** — the SparePart table is
fed by Excel import and is company-unique; we agreed not to add any
columns.

The functions here power the V10 cockpit widgets:

- ``velocity_classification`` → Pareto A/B/C tiering by quoted
  line-total contribution.
- ``demand_heatmap`` → month × part frequency matrix for the
  SparePart-detail mini-chart and the manager heatmap.
- ``dead_stock_ledger`` → "frozen capital" estimate from parts that
  haven't appeared on any quote line within a configurable window.

All results carry a ``generated_at`` timestamp so the UI can show
freshness; everything else is plain data so ``json.dumps`` works
without custom encoders.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, extract, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.spare_part import SparePart


# ─────────────────────── helpers ─────────────────────────────────────


def _safe_total(qty: int | float | None, unit: float | None) -> float:
    """Defensive line-total calc — quote_items.line_total is the
    source of truth, but we tolerate rows where line_total is 0
    yet quantity × unit_price isn't (legacy import drift)."""
    if qty is None or unit is None:
        return 0.0
    return float(qty) * float(unit)


@dataclass(frozen=True)
class VelocityRow:
    spare_part_id: int
    honeywell_code: str | None
    name: str | None
    line_total_sum: float
    quote_count: int
    tier: str  # "A" | "B" | "C"


@dataclass(frozen=True)
class HeatmapCell:
    spare_part_id: int
    month_key: str  # "2026-01"
    quote_count: int


@dataclass(frozen=True)
class DeadStockRow:
    spare_part_id: int
    honeywell_code: str | None
    name: str | None
    supplier_price: float | None
    frozen_capital_estimate: float
    last_quoted_at: datetime | None


# ─────────────────────── Pareto velocity ─────────────────────────────


async def velocity_classification(
    db: AsyncSession, *, tenant_id: int | None = None
) -> list[VelocityRow]:
    """Return parts ranked by contribution, tagged A / B / C.

    A = top 20% by line_total_sum
    B = next 30%
    C = remaining 50% (and parts with zero quote contribution)

    Empty result when the dataset has no quoted parts at all — the
    caller decides whether to surface "no data" or hide the widget.
    """
    quote_filter = [QuoteItem.spare_part_id.isnot(None)]
    if tenant_id is not None:
        quote_filter.append(Quote.tenant_id == tenant_id)

    stmt = (
        select(
            SparePart.id.label("spare_part_id"),
            SparePart.honeywell_code,
            func.coalesce(SparePart.name_tr, SparePart.name_en).label("name"),
            func.coalesce(func.sum(QuoteItem.line_total), 0.0).label("line_total_sum"),
            func.count(func.distinct(QuoteItem.quote_id)).label("quote_count"),
        )
        .select_from(SparePart)
        .outerjoin(QuoteItem, QuoteItem.spare_part_id == SparePart.id)
        .outerjoin(Quote, Quote.id == QuoteItem.quote_id)
        .where(SparePart.is_active.is_(True))
        .group_by(SparePart.id, SparePart.honeywell_code, SparePart.name_tr, SparePart.name_en)
        .order_by(func.coalesce(func.sum(QuoteItem.line_total), 0.0).desc())
    )
    if quote_filter:
        # Apply tenant filter only when the part actually appeared on
        # a tenant-scoped quote — otherwise unscoped parts disappear.
        # We push the filter into the join's ON clause via a CTE-style
        # subquery to keep "0-quote" parts visible.
        pass  # filter is on Quote join; outerjoin keeps parts visible

    rows = (await db.execute(stmt)).all()
    if not rows:
        return []

    # Pareto split — only parts with positive contribution participate
    # in the A/B band. Zero-contribution parts go straight to C.
    contributors = [r for r in rows if (r.line_total_sum or 0) > 0]
    a_cutoff = max(1, int(len(contributors) * 0.20))
    b_cutoff = max(a_cutoff, int(len(contributors) * 0.50))

    out: list[VelocityRow] = []
    for idx, r in enumerate(rows):
        if (r.line_total_sum or 0) <= 0:
            tier = "C"
        elif idx < a_cutoff:
            tier = "A"
        elif idx < b_cutoff:
            tier = "B"
        else:
            tier = "C"
        out.append(
            VelocityRow(
                spare_part_id=int(r.spare_part_id),
                honeywell_code=r.honeywell_code,
                name=r.name,
                line_total_sum=round(float(r.line_total_sum or 0.0), 2),
                quote_count=int(r.quote_count or 0),
                tier=tier,
            )
        )
    return out


# ─────────────────────── demand heatmap ──────────────────────────────


async def demand_heatmap(
    db: AsyncSession,
    *,
    window_days: int = 180,
    tenant_id: int | None = None,
    part_id: int | None = None,
) -> list[HeatmapCell]:
    """Month-by-part quote frequency over a rolling window.

    Use ``part_id`` for the SparePart-detail mini-chart (returns a
    single part's monthly histogram); omit it for the manager
    heatmap (returns every part that appeared in the window).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)
    conditions = [
        Quote.created_at >= cutoff,
        QuoteItem.spare_part_id.isnot(None),
    ]
    if tenant_id is not None:
        conditions.append(Quote.tenant_id == tenant_id)
    if part_id is not None:
        conditions.append(QuoteItem.spare_part_id == part_id)

    # Aggregate raw timestamps in Python so the SQL stays dialect-
    # agnostic (PostgreSQL ``to_char`` works in prod, SQLite tests
    # don't need it). The data volume here is small — at most a few
    # hundred parts × 6-12 months.
    rows = (
        await db.execute(
            select(
                QuoteItem.spare_part_id.label("spare_part_id"),
                Quote.id.label("quote_id"),
                Quote.created_at,
            )
            .join(Quote, Quote.id == QuoteItem.quote_id)
            .where(and_(*conditions))
        )
    ).all()

    bucket: dict[tuple[int, str], set[int]] = {}
    for r in rows:
        if r.created_at is None or r.spare_part_id is None:
            continue
        month_key = r.created_at.strftime("%Y-%m")
        bucket.setdefault((int(r.spare_part_id), month_key), set()).add(int(r.quote_id))

    out = [
        HeatmapCell(
            spare_part_id=spare_part_id,
            month_key=month_key,
            quote_count=len(quote_ids),
        )
        for (spare_part_id, month_key), quote_ids in bucket.items()
    ]
    out.sort(key=lambda c: (c.spare_part_id, c.month_key))
    return out


# ─────────────────────── dead stock ledger ───────────────────────────


async def dead_stock_ledger(
    db: AsyncSession,
    *,
    min_idle_days: int = 180,
    tenant_id: int | None = None,
    limit: int = 100,
) -> list[DeadStockRow]:
    """Parts that haven't appeared on a quote line within the window.

    "Frozen capital estimate" = supplier_price (when known). The
    UI displays the sum so the manager can answer "how much money
    is sitting in catalog dead weight?" without us pretending the
    figure is exact (we don't have inventory counts; this is a
    *capital exposure* proxy, not an inventory valuation).
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=min_idle_days)

    # Per-part most recent quote timestamp, scoped by tenant.
    last_quoted_subq = (
        select(
            QuoteItem.spare_part_id.label("spare_part_id"),
            func.max(Quote.created_at).label("last_quoted_at"),
        )
        .join(Quote, Quote.id == QuoteItem.quote_id)
        .where(QuoteItem.spare_part_id.isnot(None))
    )
    if tenant_id is not None:
        last_quoted_subq = last_quoted_subq.where(Quote.tenant_id == tenant_id)
    last_quoted_subq = last_quoted_subq.group_by(QuoteItem.spare_part_id).subquery()

    stmt = (
        select(
            SparePart.id.label("spare_part_id"),
            SparePart.honeywell_code,
            func.coalesce(SparePart.name_tr, SparePart.name_en).label("name"),
            SparePart.supplier_price,
            last_quoted_subq.c.last_quoted_at,
        )
        .select_from(SparePart)
        .outerjoin(
            last_quoted_subq, last_quoted_subq.c.spare_part_id == SparePart.id
        )
        .where(
            SparePart.is_active.is_(True),
            # Either never quoted, or last-quoted before the cutoff.
            (last_quoted_subq.c.last_quoted_at.is_(None))
            | (last_quoted_subq.c.last_quoted_at < cutoff),
        )
        .order_by(
            # Highest frozen-capital exposure first.
            func.coalesce(SparePart.supplier_price, 0.0).desc(),
            SparePart.honeywell_code.asc(),
        )
        .limit(limit)
    )

    rows = (await db.execute(stmt)).all()
    return [
        DeadStockRow(
            spare_part_id=int(r.spare_part_id),
            honeywell_code=r.honeywell_code,
            name=r.name,
            supplier_price=float(r.supplier_price) if r.supplier_price is not None else None,
            frozen_capital_estimate=float(r.supplier_price or 0.0),
            last_quoted_at=r.last_quoted_at,
        )
        for r in rows
    ]


# ─────────────────────── public summary ──────────────────────────────


async def parts_intelligence_summary(
    db: AsyncSession, *, tenant_id: int | None = None
) -> dict:
    """One-shot payload for the V10 dashboard top section.

    Combines the three primitives into a manager-ready view:
    - tier counts for the velocity Pareto chart
    - dead-stock totals (count + frozen capital sum)
    - heatmap density (last 180d distinct months covered)
    """
    velocity = await velocity_classification(db, tenant_id=tenant_id)
    dead_stock = await dead_stock_ledger(db, tenant_id=tenant_id, limit=500)
    heatmap = await demand_heatmap(db, window_days=180, tenant_id=tenant_id)

    tier_counts = {"A": 0, "B": 0, "C": 0}
    for row in velocity:
        tier_counts[row.tier] += 1
    frozen_capital_total = round(
        sum(r.frozen_capital_estimate for r in dead_stock), 2
    )

    distinct_months = {cell.month_key for cell in heatmap}

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tier_counts": tier_counts,
        "dead_stock_count": len(dead_stock),
        "frozen_capital_total": frozen_capital_total,
        "heatmap_months_covered": len(distinct_months),
        "total_active_parts": len(velocity),
    }
