"""Shared rate limiter — FastAPI dependencies for route-specific limits.

Note: slowapi decorator @limiter.limit() conflicts with FastAPI's
`from __future__ import annotations` + slowapi's functools.wraps combination
(ForwardRef resolution breaks). We expose dependency helpers instead.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Global limiter for middleware-level default limits
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_API])


# ── Route-specific dependency-based rate limiting (in-memory) ──
# Simple sliding-window counter. For multi-worker deploys, replace with Redis.

_login_attempts: dict[str, deque] = defaultdict(deque)
_lock = Lock()


def _parse_rate(rate: str) -> tuple[int, int]:
    """Parse '5/minute' → (5, 60)."""
    count_str, period = rate.split("/")
    count = int(count_str)
    period_seconds = {
        "second": 1,
        "minute": 60,
        "hour": 3600,
        "day": 86400,
    }.get(period.lower().rstrip("s"), 60)
    return count, period_seconds


def _get_client_ip(request: Request) -> str:
    """Prefer X-Forwarded-For when behind a proxy (Render)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce_login_rate_limit(request: Request) -> None:
    """Dependency: enforce strict rate limit on auth endpoints.

    Defaults to settings.RATE_LIMIT_LOGIN (e.g. '5/minute').
    Raises 429 on breach. Key: client IP.
    """
    limit_count, window = _parse_rate(settings.RATE_LIMIT_LOGIN)
    ip = _get_client_ip(request)
    now = time.time()

    with _lock:
        dq = _login_attempts[ip]
        # Drop expired entries
        while dq and dq[0] < now - window:
            dq.popleft()
        if len(dq) >= limit_count:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Cok fazla istek. Lutfen birkac dakika bekleyin.",
                headers={"Retry-After": str(window)},
            )
        dq.append(now)
