"""Redis client singleton for shared state across workers.

Used for: JWT revocation, rate limiting, parts cache, parse metrics.
Falls back gracefully if Redis is unavailable (logs warning, uses in-memory).
"""

import logging

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis | None:
    """Get the shared async Redis client. Returns None if not configured."""
    global _redis
    if _redis is None and settings.REDIS_URL:
        try:
            _redis = aioredis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
        except Exception as e:
            logger.warning("Redis connection failed: %s", e)
    return _redis


async def close_redis() -> None:
    """Close the Redis connection pool."""
    global _redis
    if _redis:
        await _redis.aclose()
        _redis = None
