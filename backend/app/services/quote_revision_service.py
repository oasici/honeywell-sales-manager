"""Quote revision tree service (V9).

V2 Faz 3.4 #24 — multiple quote revisions under one opportunity.
``parent_quote_id`` walks back to the original; ``superseded_by``
points forward to the next revision; ``revision_no`` is the human-
readable counter.

Public surface:
- ``create_revision(quote_id)`` — clone + bump revision_no + link
- ``list_tree(opportunity_id)`` — walk every revision chain on the opp
- ``get_chain(quote_id)`` — original → … → latest for a single quote
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quote import Quote
from app.models.quote_item import QuoteItem

logger = logging.getLogger(__name__)


# ─────────────────────── helpers ─────────────────────────────────────


async def _root_id(db: AsyncSession, quote_id: int) -> int:
    """Walk parent links back to the original quote."""
    cursor = quote_id
    visited: set[int] = set()
    while True:
        if cursor in visited:
            return cursor  # cycle guard
        visited.add(cursor)
        q = await db.get(Quote, cursor)
        if q is None or q.parent_quote_id is None:
            return cursor
        cursor = int(q.parent_quote_id)


async def _next_revision_no(db: AsyncSession, root_id: int) -> int:
    rows = (
        await db.execute(
            select(Quote.revision_no)
            .where((Quote.id == root_id) | (Quote.parent_quote_id == root_id))
        )
    ).scalars().all()
    return (max(rows) if rows else 0) + 1


# ─────────────────────── create_revision ─────────────────────────────


async def create_revision(
    db: AsyncSession, *, quote_id: int, created_by: int | None = None
) -> Quote | None:
    """Clone ``quote_id`` into a new revision.

    Carries over line items, financial totals, customer + currency. The
    new revision starts in ``draft`` status; old quote is flagged
    ``superseded_by`` the new id.
    """
    src = await db.get(Quote, quote_id)
    if src is None:
        return None

    root_id = await _root_id(db, quote_id)
    rev_no = await _next_revision_no(db, root_id)

    new_quote = Quote(
        quote_number=f"{src.quote_number}-r{rev_no}",
        customer_id=src.customer_id,
        email_request_id=src.email_request_id,
        created_by=created_by or src.created_by,
        status="draft",
        language=src.language,
        currency=src.currency,
        subtotal=src.subtotal,
        discount_total=src.discount_total,
        tax_rate=src.tax_rate,
        tax_amount=src.tax_amount,
        grand_total=src.grand_total,
        valid_days=src.valid_days,
        notes=src.notes,
        parent_quote_id=root_id,
        revision_no=rev_no,
        tenant_id=getattr(src, "tenant_id", None),
    )
    db.add(new_quote)
    await db.flush()

    # Mirror line items.
    items = (
        await db.execute(select(QuoteItem).where(QuoteItem.quote_id == quote_id))
    ).scalars().all()
    for it in items:
        db.add(
            QuoteItem(
                quote_id=new_quote.id,
                spare_part_id=it.spare_part_id,
                quantity=it.quantity,
                unit_price=it.unit_price,
                discount_pct=it.discount_pct,
                line_total=it.line_total,
                description=it.description,
            )
        )

    # Old quote points forward to the new revision.
    src.superseded_by = new_quote.id
    await db.flush()
    return new_quote


# ─────────────────────── list / read ─────────────────────────────────


async def get_chain(db: AsyncSession, *, quote_id: int) -> list[Quote]:
    """Return the full chain rooted at ``quote_id``'s root, ordered by revision_no."""
    root_id = await _root_id(db, quote_id)
    rows = (
        await db.execute(
            select(Quote)
            .where((Quote.id == root_id) | (Quote.parent_quote_id == root_id))
            .order_by(Quote.revision_no.asc())
        )
    ).scalars().all()
    return list(rows)


async def list_tree(
    db: AsyncSession, *, opportunity_id: int
) -> list[dict]:
    """All revision chains for the customer's quotes on this opportunity.

    Joining via ``Opportunity.customer_id`` keeps this resilient when
    the eventual ``quotes.opportunity_id`` direct link arrives — the
    same query still works.
    """
    from app.models.opportunity import Opportunity

    opp = await db.get(Opportunity, opportunity_id)
    if opp is None or opp.customer_id is None:
        return []

    quotes = (
        await db.execute(
            select(Quote)
            .where(Quote.customer_id == opp.customer_id)
            .order_by(Quote.id.asc())
        )
    ).scalars().all()

    by_root: dict[int, list[Quote]] = {}
    roots: list[int] = []
    for q in quotes:
        root_id = q.parent_quote_id or q.id
        if q.parent_quote_id is None and q.id not in roots:
            roots.append(q.id)
        by_root.setdefault(root_id, []).append(q)

    out: list[dict] = []
    for root_id in roots:
        chain = sorted(by_root.get(root_id, []), key=lambda x: x.revision_no)
        out.append(
            {
                "root_quote_id": root_id,
                "revision_count": len(chain),
                "latest_status": chain[-1].status if chain else None,
                "revisions": [
                    {
                        "id": q.id,
                        "quote_number": q.quote_number,
                        "revision_no": q.revision_no,
                        "status": q.status,
                        "grand_total": q.grand_total,
                        "currency": q.currency,
                        "created_at": q.created_at.isoformat() if q.created_at else None,
                        "superseded_by": q.superseded_by,
                    }
                    for q in chain
                ],
            }
        )
    return out
