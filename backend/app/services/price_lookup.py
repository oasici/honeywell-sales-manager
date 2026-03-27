"""Price resolution service for spare parts."""

import logging
from datetime import date, timezone, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.price_entry import PriceEntry

logger = logging.getLogger(__name__)


async def get_best_price(
    db: AsyncSession, spare_part_id: int, currency: str = "USD"
) -> dict | None:
    """Get best current price for a spare part.

    Priority:
    1. Valid date range (today within valid_from..valid_until) + same currency
    2. Same currency, most recent
    3. Any currency, most recent

    Returns: {list_price, discount_pct, net_price, currency} or None.
    """
    today = date.today()

    stmt = (
        select(PriceEntry)
        .where(PriceEntry.spare_part_id == spare_part_id)
        .order_by(PriceEntry.created_at.desc())
    )
    result = await db.execute(stmt)
    entries: list[PriceEntry] = list(result.scalars().all())

    if not entries:
        logger.debug("No prices found for spare_part_id=%d", spare_part_id)
        return None

    # Priority 1: Valid date range + matching currency
    for entry in entries:
        if entry.currency.upper() != currency.upper():
            continue
        if _is_date_valid(entry, today):
            return _to_dict(entry)

    # Priority 2: Valid date range, any currency
    for entry in entries:
        if _is_date_valid(entry, today):
            return _to_dict(entry)

    # Priority 3: Same currency, most recent (already ordered by created_at desc)
    for entry in entries:
        if entry.currency.upper() == currency.upper():
            return _to_dict(entry)

    # Priority 4: Any currency, most recent
    return _to_dict(entries[0])


def _is_date_valid(entry: PriceEntry, today: date) -> bool:
    """Check if a price entry is within its valid date range."""
    if entry.valid_from and entry.valid_from > today:
        return False
    if entry.valid_until and entry.valid_until < today:
        return False
    # At least one date bound must be set for it to be a "date-range" entry
    return entry.valid_from is not None or entry.valid_until is not None


def _to_dict(entry: PriceEntry) -> dict:
    return {
        "price_entry_id": entry.id,
        "list_price": entry.list_price,
        "discount_pct": entry.discount_pct,
        "net_price": entry.net_price,
        "currency": entry.currency,
        "valid_from": entry.valid_from.isoformat() if entry.valid_from else None,
        "valid_until": entry.valid_until.isoformat() if entry.valid_until else None,
        "price_list_version": entry.price_list_version,
    }


def calculate_line_total(
    quantity: int, unit_price: float, discount_pct: float = 0.0
) -> float:
    """Calculate line total with discount.

    line_total = quantity * unit_price * (1 - discount_pct / 100)
    """
    if discount_pct < 0 or discount_pct > 100:
        raise ValueError(f"discount_pct must be between 0 and 100, got {discount_pct}")
    return round(quantity * unit_price * (1 - discount_pct / 100), 2)
