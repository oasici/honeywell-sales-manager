"""V10 Sprint EE — substitution patterns + cross-customer demand.

Three derivations on top of V9's quote revision tree and the existing
QuoteItem × Customer relationship:

- ``substitution_patterns(part_id)`` — uses the
  ``parent_quote_id`` revision chain to detect "part swapped".
  Each parent→child pair is diffed; when a part appears in the
  parent but a different part replaces it in the child, that's a
  substitution event. Aggregated by (original, replacement) we get
  "what does this part normally get swapped with".
- ``cross_customer_demand(part_id)`` — distinct customers and
  industries that have quoted this part in the last N months.
- ``segment_affinity(part_id)`` — which customer ``industry``
  values consume this part most. Powers the "Bu parça {industry}
  segmentinde popüler" suggestion.

All functions are tenant-scoped; pass ``tenant_id=None`` for
single-tenant deployments.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer import Customer
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.spare_part import SparePart


@dataclass(frozen=True)
class SubstitutionPattern:
    original_part_id: int
    replacement_part_id: int | None
    replacement_code: str | None
    replacement_name: str | None
    occurrence_count: int


@dataclass(frozen=True)
class CrossCustomerRow:
    customer_id: int
    customer_name: str | None
    company: str | None
    industry: str | None
    quote_count: int
    last_quoted_at: datetime | None


@dataclass(frozen=True)
class SegmentAffinityRow:
    industry: str
    customer_count: int
    quote_count: int


# ─────────────────────── substitution detection ──────────────────────


def _items_by_part_id(items: Sequence[QuoteItem]) -> dict[int | None, QuoteItem]:
    """Map spare_part_id → first matching item.

    A revision typically only references each part once; if not, we
    take the first occurrence — adequate for substitution heuristics.
    """
    out: dict[int | None, QuoteItem] = {}
    for item in items:
        if item.spare_part_id is None:
            continue
        out.setdefault(int(item.spare_part_id), item)
    return out


async def substitution_patterns(
    db: AsyncSession,
    *,
    part_id: int,
    tenant_id: int | None = None,
    limit: int = 20,
) -> list[SubstitutionPattern]:
    """Detect what ``part_id`` typically gets swapped for.

    Walks every parent→child quote revision pair where the parent
    contained ``part_id`` and the child does not. For each such
    pair, the *new* parts that appear in the child (not in the
    parent) are candidates for "what replaced it". We aggregate
    across pairs; the most common replacement floats to the top.

    Edge cases:
    - Revision where line items are unchanged (descriptive-only
      change) → emits no substitution.
    - Multiple new parts in the child → each one gets +1 count
      (we don't try to attribute exactly which replaced which).
    """
    revision_filter = [
        Quote.parent_quote_id.isnot(None),
    ]
    if tenant_id is not None:
        revision_filter.append(Quote.tenant_id == tenant_id)

    children = (
        await db.execute(
            select(Quote)
            .options(selectinload(Quote.items))
            .where(and_(*revision_filter))
        )
    ).scalars().all()

    counts: Counter[int | None] = Counter()
    for child in children:
        parent = await db.get(Quote, int(child.parent_quote_id))
        if parent is None:
            continue
        # Re-fetch parent with items for the diff.
        parent = (
            await db.execute(
                select(Quote)
                .options(selectinload(Quote.items))
                .where(Quote.id == parent.id)
            )
        ).scalar_one()

        parent_items = _items_by_part_id(parent.items)
        if part_id not in parent_items:
            continue
        child_items = _items_by_part_id(child.items)
        if part_id in child_items:
            # Same part survived the revision → not a substitution.
            continue
        new_parts = set(child_items.keys()) - set(parent_items.keys())
        if not new_parts:
            continue
        for new_id in new_parts:
            counts[int(new_id)] += 1

    if not counts:
        return []

    top = counts.most_common(limit)
    out: list[SubstitutionPattern] = []
    for replacement_id, occurrences in top:
        replacement = (
            await db.get(SparePart, int(replacement_id)) if replacement_id else None
        )
        out.append(
            SubstitutionPattern(
                original_part_id=part_id,
                replacement_part_id=int(replacement_id) if replacement_id else None,
                replacement_code=replacement.honeywell_code if replacement else None,
                replacement_name=(replacement.name_tr or replacement.name_en)
                if replacement
                else None,
                occurrence_count=int(occurrences),
            )
        )
    return out


# ─────────────────────── cross-customer demand ───────────────────────


async def cross_customer_demand(
    db: AsyncSession,
    *,
    part_id: int,
    tenant_id: int | None = None,
    months: int = 12,
    limit: int = 50,
) -> list[CrossCustomerRow]:
    """Distinct customers that have quoted ``part_id`` recently.

    Used by the SparePart detail "Bu parça X müşteride kullanılıyor"
    section. Returns at most ``limit`` rows, sorted by recency.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    conditions = [
        QuoteItem.spare_part_id == part_id,
        Quote.created_at >= cutoff,
        Quote.customer_id.isnot(None),
    ]
    if tenant_id is not None:
        conditions.append(Quote.tenant_id == tenant_id)

    rows = (
        await db.execute(
            select(
                Customer.id.label("customer_id"),
                Customer.name,
                Customer.company,
                Customer.industry,
                func.count(func.distinct(Quote.id)).label("quote_count"),
                func.max(Quote.created_at).label("last_quoted_at"),
            )
            .select_from(QuoteItem)
            .join(Quote, Quote.id == QuoteItem.quote_id)
            .join(Customer, Customer.id == Quote.customer_id)
            .where(and_(*conditions))
            .group_by(Customer.id, Customer.name, Customer.company, Customer.industry)
            .order_by(func.max(Quote.created_at).desc())
            .limit(limit)
        )
    ).all()

    return [
        CrossCustomerRow(
            customer_id=int(r.customer_id),
            customer_name=r.name,
            company=r.company,
            industry=r.industry,
            quote_count=int(r.quote_count or 0),
            last_quoted_at=r.last_quoted_at,
        )
        for r in rows
    ]


# ─────────────────────── segment affinity ────────────────────────────


async def segment_affinity(
    db: AsyncSession,
    *,
    part_id: int,
    tenant_id: int | None = None,
    months: int = 12,
) -> list[SegmentAffinityRow]:
    """Which industries quote this part most.

    Returns a list sorted by quote_count descending. Rows where
    industry is NULL are skipped — they'd compress every "unset"
    customer into one row that's not actionable.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)
    conditions = [
        QuoteItem.spare_part_id == part_id,
        Quote.created_at >= cutoff,
        Customer.industry.isnot(None),
    ]
    if tenant_id is not None:
        conditions.append(Quote.tenant_id == tenant_id)

    rows = (
        await db.execute(
            select(
                Customer.industry.label("industry"),
                func.count(func.distinct(Customer.id)).label("customer_count"),
                func.count(func.distinct(Quote.id)).label("quote_count"),
            )
            .select_from(QuoteItem)
            .join(Quote, Quote.id == QuoteItem.quote_id)
            .join(Customer, Customer.id == Quote.customer_id)
            .where(and_(*conditions))
            .group_by(Customer.industry)
            .order_by(func.count(func.distinct(Quote.id)).desc())
        )
    ).all()

    return [
        SegmentAffinityRow(
            industry=str(r.industry),
            customer_count=int(r.customer_count or 0),
            quote_count=int(r.quote_count or 0),
        )
        for r in rows
    ]
