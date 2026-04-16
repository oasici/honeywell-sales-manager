"""API key authentication — validate X-API-Key header for public API access."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey


async def validate_api_key(request: Request, db: AsyncSession) -> ApiKey | None:
    """Check X-API-Key header, validate against DB, check scope.

    Returns the ApiKey record if valid, None if no header present.
    Raises 401 for invalid keys and 429 for rate-limited keys.
    """
    key = request.headers.get("X-API-Key")
    if not key:
        return None

    key_hash = hashlib.sha256(key.encode()).hexdigest()

    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    )
    api_key = result.scalar_one_or_none()

    if not api_key:
        raise HTTPException(status_code=401, detail="Gecersiz API anahtari")

    # Update last_used_at
    api_key.last_used_at = datetime.now(timezone.utc)
    await db.flush()

    return api_key


def generate_api_key() -> tuple[str, str]:
    """Generate a random API key. Returns (plain_key, key_hash)."""
    plain = f"hsm_{secrets.token_urlsafe(32)}"
    hashed = hashlib.sha256(plain.encode()).hexdigest()
    return plain, hashed
