"""Security utilities: JWT, password hashing, token management."""

import hashlib
import secrets
import re
import threading
from collections import OrderedDict
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── In-memory revoked token store (bounded, thread-safe) ──
# NOTE: This is a single-process solution. Multiple Uvicorn workers or
#       multiple instances (e.g. Render auto-scale) do NOT share this store.
#       For multi-instance deployments, replace with Redis or a DB table:
#         1. Add `revoked_tokens` table (jti VARCHAR PK, revoked_at TIMESTAMP)
#         2. On revoke: INSERT jti
#         3. On decode: SELECT EXISTS(jti)
#         4. Periodic cleanup: DELETE WHERE revoked_at < now() - max_token_lifetime
# Short-term mitigation: access token TTL is 30 min, limiting exposure window.
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
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    jti = _generate_jti()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh", "jti": jti})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        jti = payload.get("jti")
        if jti:
            with _revoked_lock:
                if jti in _revoked_jti:
                    return None
        return payload
    except JWTError:
        return None


def revoke_token(token: str) -> None:
    """Add token's jti to the bounded revocation store (FIFO eviction)."""
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        jti = payload.get("jti")
        if jti:
            with _revoked_lock:
                _revoked_jti[jti] = None
                _revoked_jti.move_to_end(jti)
                while len(_revoked_jti) > MAX_REVOKED_TOKENS:
                    _revoked_jti.popitem(last=False)
    except JWTError:
        pass


# ── CSRF ──

def generate_csrf_token() -> str:
    """Generate a CSRF token."""
    return secrets.token_hex(32)


def verify_csrf_token(token: str, expected: str) -> bool:
    """Constant-time comparison of CSRF tokens."""
    return secrets.compare_digest(token, expected)


# ── Sanitization ──

def sanitize_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal."""
    # Remove path separators and null bytes
    name = filename.replace("/", "").replace("\\", "").replace("\x00", "")
    # Remove leading dots (hidden files / traversal)
    name = name.lstrip(".")
    # If empty after sanitization, use a default
    return name or "uploaded_file"


def is_safe_path(base_dir: str, target_path: str) -> bool:
    """Check that target_path is within base_dir (prevents path traversal)."""
    import os
    base = os.path.abspath(base_dir)
    target = os.path.abspath(target_path)
    return target.startswith(base + os.sep) or target == base
