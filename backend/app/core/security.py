"""Security utilities: JWT, password hashing, token management.

JWT revocation uses Redis when available (multi-worker safe).
Falls back to in-memory OrderedDict for single-worker/dev.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import re
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from jwt.exceptions import PyJWTError as JWTError
from passlib.context import CryptContext

from app.core.config import settings

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── In-memory fallback (used when Redis unavailable) ──
MAX_REVOKED_TOKENS = 10_000
_revoked_lock = threading.Lock()
_revoked_jti: OrderedDict[str, None] = OrderedDict()


# ── Password ──

def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


PASSWORD_MIN_LENGTH = 8
PASSWORD_PATTERN = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$"
)


def validate_password_strength(password: str) -> str | None:
    """Return error message if password is weak, None if OK."""
    if len(password) < PASSWORD_MIN_LENGTH:
        return f"Sifre en az {PASSWORD_MIN_LENGTH} karakter olmali"
    if not PASSWORD_PATTERN.match(password):
        return "Sifre en az 1 buyuk harf, 1 kucuk harf ve 1 rakam icermeli"
    return None


# ── JWT ──

def _generate_jti() -> str:
    """Generate a unique token ID for revocation tracking."""
    return secrets.token_hex(16)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    jti = _generate_jti()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access", "jti": jti})
    return pyjwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    jti = _generate_jti()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": jti})
    return pyjwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _is_revoked_memory(jti: str) -> bool:
    """Check in-memory fallback store."""
    with _revoked_lock:
        return jti in _revoked_jti


def _revoke_memory(jti: str, ttl_seconds: int) -> None:
    """Add to in-memory fallback store."""
    with _revoked_lock:
        _revoked_jti[jti] = None
        _revoked_jti.move_to_end(jti)
        while len(_revoked_jti) > MAX_REVOKED_TOKENS:
            _revoked_jti.popitem(last=False)


def _try_redis_revoke(jti: str, ttl_seconds: int) -> bool:
    """Best-effort Redis revoke from sync context.

    We never call ``asyncio.run`` here: if there is a running event loop
    (the common case in FastAPI) we return ``False`` so the caller
    falls back to the in-memory store. Fully async call sites should use
    :func:`revoke_token_async` for Redis-backed multi-worker revocation.
    """
    return False


def decode_token(token: str) -> dict | None:
    """Sync JWT decode.

    Only validates signature + expiry and checks the in-memory revocation
    list. Use :func:`decode_token_async` from FastAPI async endpoints to
    additionally hit Redis for multi-worker revocation safety.
    """
    try:
        payload = pyjwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        jti = payload.get("jti")
        if jti and _is_revoked_memory(jti):
            return None
        return payload
    except JWTError:
        return None


async def decode_token_async(token: str) -> dict | None:
    """Async version that checks Redis first, then memory fallback."""
    try:
        payload = pyjwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        jti = payload.get("jti")
        if not jti:
            return payload

        # Try Redis first
        try:
            from app.core.redis_client import get_redis
            r = get_redis()
            if r:
                is_revoked = await r.exists(f"revoked:{jti}")
                if is_revoked:
                    return None
                return payload
        except Exception:
            pass

        # Fallback to memory
        if _is_revoked_memory(jti):
            return None
        return payload
    except JWTError:
        return None


def revoke_token(token: str) -> None:
    """Sync revocation — uses in-memory store. For multi-worker, use revoke_token_async."""
    try:
        payload = pyjwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        jti = payload.get("jti")
        if jti:
            ttl = int(payload.get("exp", 0) - datetime.now(timezone.utc).timestamp())
            ttl = max(ttl, 60)
            if not _try_redis_revoke(jti, ttl):
                _revoke_memory(jti, ttl)
    except JWTError:
        pass


async def revoke_token_async(token: str) -> None:
    """Async revocation — uses Redis (multi-worker safe) + memory fallback."""
    try:
        payload = pyjwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        jti = payload.get("jti")
        if not jti:
            return

        ttl = int(payload.get("exp", 0) - datetime.now(timezone.utc).timestamp())
        ttl = max(ttl, 60)

        # Try Redis
        try:
            from app.core.redis_client import get_redis
            r = get_redis()
            if r:
                await r.setex(f"revoked:{jti}", ttl, "1")
                return
        except Exception as e:
            logger.debug("Redis revoke failed, using memory fallback: %s", e)

        # Fallback
        _revoke_memory(jti, ttl)
    except JWTError:
        pass


# ── CSRF (double-submit cookie pattern) ──
# Used when clients authenticate via HttpOnly cookie. The `csrf_token` cookie
# is readable by JS (not HttpOnly); the frontend echoes it in the
# `X-CSRF-Token` header on every state-changing request. The middleware
# compares the two — a same-origin attacker cannot set a cross-origin header.

def generate_csrf_token() -> str:
    """Generate a cryptographically-random CSRF token."""
    return secrets.token_hex(32)


def verify_csrf_token(token: str, expected: str) -> bool:
    """Constant-time CSRF token comparison (timing-attack resistant)."""
    if not token or not expected:
        return False
    return secrets.compare_digest(token, expected)


# ── Sanitization ──

def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal."""
    name = filename.replace("/", "").replace("\\", "").replace("\x00", "")
    name = name.lstrip(".")
    return name or "uploaded_file"


def is_safe_path(base_dir: str, target_path: str) -> bool:
    """Check that target_path is within base_dir (prevents path traversal)."""
    import os
    base = os.path.abspath(base_dir)
    target = os.path.abspath(target_path)
    return target.startswith(base + os.sep) or target == base
