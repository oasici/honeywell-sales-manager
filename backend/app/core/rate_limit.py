"""Shared rate limiter — FastAPI dependencies for route-specific limits.

Note: slowapi decorator @limiter.limit() conflicts with FastAPI's
`from __future__ import annotations` + slowapi's functools.wraps combination
(ForwardRef resolution breaks). We expose dependency helpers instead.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock

from fastapi import Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings

# Global limiter for middleware-level default limits
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_API])


# ── Route-specific dependency-based rate limiting (in-memory) ──
# Simple sliding-window counter. For multi-worker deploys, replace with Redis.

_login_attempts: dict[str, deque] = defaultdict(deque)
_ai_attempts: dict[str, deque] = defaultdict(deque)
_upload_attempts: dict[str, deque] = defaultdict(deque)
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


def _enforce_window(
    bucket: dict[str, deque],
    key: str,
    rate: str,
    detail: str,
) -> None:
    """Sliding-window rate limit shared across login/AI/upload enforcers."""
    limit_count, window = _parse_rate(rate)
    now = time.time()

    with _lock:
        dq = bucket[key]
        while dq and dq[0] < now - window:
            dq.popleft()
        if len(dq) >= limit_count:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail,
                headers={"Retry-After": str(window)},
            )
        dq.append(now)


async def enforce_login_rate_limit(request: Request) -> None:
    """Dependency: enforce strict rate limit on auth endpoints.

    Defaults to settings.RATE_LIMIT_LOGIN (e.g. '5/minute').
    Raises 429 on breach. Key: client IP.
    """
    _enforce_window(
        _login_attempts,
        _get_client_ip(request),
        settings.RATE_LIMIT_LOGIN,
        "Cok fazla istek. Lutfen birkac dakika bekleyin.",
    )


def make_user_rate_limit(
    bucket: dict[str, deque],
    rate_setting_name: str,
    detail: str,
):
    """Build a FastAPI dependency that limits a user (or IP) sliding window.

    Resolves the current user via ``get_current_user`` to key the bucket per
    user-id. When auth is missing or fails, falls back to client IP — this
    keeps the limiter useful for unauthenticated entrypoints without
    coupling all callers to auth.
    """

    # Imported lazily to avoid a config -> dependencies -> models import cycle.
    from app.core.dependencies import get_current_user

    async def _dep(
        request: Request,
        current_user=Depends(get_current_user),
    ) -> None:
        if current_user is not None and getattr(current_user, "id", None) is not None:
            key = f"user:{current_user.id}"
        else:
            key = f"ip:{_get_client_ip(request)}"
        rate = getattr(settings, rate_setting_name)
        _enforce_window(bucket, key, rate, detail)

    return _dep


enforce_ai_rate_limit = make_user_rate_limit(
    _ai_attempts,
    "RATE_LIMIT_AI",
    "AI istekleri icin limit asildi. Bir dakika sonra tekrar deneyin.",
)
"""Rate-limit AI endpoints (cost amplification protection). Per-user."""

enforce_upload_rate_limit = make_user_rate_limit(
    _upload_attempts,
    "RATE_LIMIT_UPLOAD",
    "Yukleme limiti asildi. Lutfen birkac dakika bekleyin.",
)
"""Rate-limit file upload endpoints (resource pressure protection). Per-user."""
