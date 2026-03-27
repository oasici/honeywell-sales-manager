"""Exchange rate service using Frankfurter API with caching."""

import logging
import time

import httpx

logger = logging.getLogger(__name__)

FRANKFURTER_API = "https://api.frankfurter.app"
CACHE_TTL_SECONDS = 3600  # 1 hour

# Module-level cache
_rates_cache: dict[str, dict[str, float]] = {}
_rates_timestamp: float = 0.0


async def get_exchange_rates(base: str = "USD") -> dict[str, float]:
    """Get exchange rates from Frankfurter API. 1-hour cache.

    Args:
        base: Base currency code (e.g., "USD", "EUR").

    Returns:
        Dict mapping currency codes to rates relative to base.
    """
    global _rates_cache, _rates_timestamp

    base = base.upper()
    now = time.time()

    # Return cached if fresh
    if base in _rates_cache and (now - _rates_timestamp) < CACHE_TTL_SECONDS:
        return _rates_cache[base]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{FRANKFURTER_API}/latest", params={"from": base})
            response.raise_for_status()
            data = response.json()

        rates = data.get("rates", {})
        # Include the base currency itself
        rates[base] = 1.0

        _rates_cache[base] = rates
        _rates_timestamp = now

        logger.info("Fetched exchange rates for base=%s: %d currencies", base, len(rates))
        return rates

    except httpx.HTTPStatusError as exc:
        logger.error(
            "Frankfurter API HTTP error %s: %s",
            exc.response.status_code,
            exc.response.text[:200],
        )
        # Return stale cache if available
        if base in _rates_cache:
            logger.warning("Returning stale cached rates for %s", base)
            return _rates_cache[base]
        raise

    except httpx.RequestError as exc:
        logger.error("Frankfurter API request error: %s", exc)
        if base in _rates_cache:
            logger.warning("Returning stale cached rates for %s", base)
            return _rates_cache[base]
        raise


async def convert_currency(amount: float, from_curr: str, to_curr: str) -> float:
    """Convert amount between currencies.

    Args:
        amount: Amount to convert.
        from_curr: Source currency code.
        to_curr: Target currency code.

    Returns:
        Converted amount, rounded to 2 decimal places.
    """
    from_curr = from_curr.upper()
    to_curr = to_curr.upper()

    if from_curr == to_curr:
        return round(amount, 2)

    rates = await get_exchange_rates(from_curr)

    if to_curr not in rates:
        raise ValueError(f"Currency '{to_curr}' not found in exchange rates for base '{from_curr}'")

    converted = amount * rates[to_curr]
    return round(converted, 2)


def clear_cache() -> None:
    """Clear the exchange rate cache (useful for testing)."""
    global _rates_cache, _rates_timestamp
    _rates_cache = {}
    _rates_timestamp = 0.0
