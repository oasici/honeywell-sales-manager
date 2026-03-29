"""Structured logging and cost tracking for email parse operations.

Logs parse metrics as JSON for monitoring dashboards and alerts.
Tracks cumulative daily API cost estimates.
"""

import json
import logging
import time
from datetime import date, datetime, timezone

_metrics_logger = logging.getLogger("app.metrics.email_parse")

ESTIMATED_COST_PER_CALL = 0.003

# Daily cost accumulator: {"2026-03-29": 0.045, ...}
_daily_cost: dict[str, float] = {}


def log_parse_metrics(
    email_id: int,
    duration_ms: int,
    parts_count: int,
    confidence: float,
    category: str,
    is_fallback: bool,
    is_skipped: bool,
    api_cost: float,
) -> None:
    """Log structured parse metrics as JSON for monitoring."""
    today = date.today().isoformat()
    daily_total = _daily_cost.get(today, 0.0) + api_cost
    _daily_cost[today] = daily_total

    metrics = {
        "event": "email_parse_complete",
        "email_id": email_id,
        "parse_duration_ms": duration_ms,
        "parts_count": parts_count,
        "confidence": round(confidence, 3),
        "category": category,
        "used_fallback": is_fallback,
        "was_skipped": is_skipped,
        "api_cost_estimate_usd": round(api_cost, 4),
        "daily_cost_total_usd": round(daily_total, 4),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _metrics_logger.info(json.dumps(metrics))


def get_daily_cost(target_date: date | None = None) -> float:
    """Get cumulative API cost for a given date (default: today)."""
    key = (target_date or date.today()).isoformat()
    return _daily_cost.get(key, 0.0)


def elapsed_ms(start: float) -> int:
    """Calculate elapsed milliseconds from a monotonic start time."""
    return int((time.monotonic() - start) * 1000)
