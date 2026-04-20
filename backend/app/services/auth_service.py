from __future__ import annotations

import logging
import time
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password, validate_password_strength
from app.models.user import User

logger = logging.getLogger(__name__)

# Account lockout: track failed attempts per email
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900  # 15 minutes
_failed_attempts: dict[str, list[float]] = defaultdict(list)


def _is_locked_out(email: str) -> tuple[bool, int]:
    """Check if email is locked out. Returns (is_locked, remaining_seconds)."""
    now = time.time()
    attempts = _failed_attempts.get(email, [])
    # Keep only attempts within lockout window
    recent = [t for t in attempts if now - t < LOCKOUT_DURATION_SECONDS]
    _failed_attempts[email] = recent

    if len(recent) >= MAX_FAILED_ATTEMPTS:
        oldest = min(recent)
        remaining = int(LOCKOUT_DURATION_SECONDS - (now - oldest))
        return True, max(remaining, 0)
    return False, 0


def _record_failed_attempt(email: str) -> None:
    _failed_attempts[email].append(time.time())


def _clear_failed_attempts(email: str) -> None:
    _failed_attempts.pop(email, None)


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    """Authenticate a user by email and password. Returns the User or None.

    Implements account lockout after 5 failed attempts (15-minute window).
    """
    # Check lockout — but still do password verification to prevent timing side-channel
    locked, remaining = _is_locked_out(email)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    # Always verify password (constant-time) to prevent timing-based user enumeration
    if user is not None:
        pw_valid = verify_password(password, user.hashed_password)
    else:
        # Hash a dummy password to keep timing consistent
        verify_password(password, hash_password("dummy-timing-pad"))
        pw_valid = False

    if locked:
        remaining_min = max(1, remaining // 60)
        logger.warning("Locked out login attempt for %s (%dmin remaining)", email, remaining_min)
        return None

    if user is None or not user.is_active or not pw_valid:
        _record_failed_attempt(email)
        return None

    # Success: clear failed attempts
    _clear_failed_attempts(email)
    return user


async def register(
    db: AsyncSession,
    email: str,
    password: str,
    full_name: str,
    role: str = "sales_rep",
) -> User:
    """Register a new user. Raises ValueError if email already exists."""
    result = await db.execute(select(User).where(User.email == email))
    existing = result.scalar_one_or_none()

    if existing is not None:
        raise ValueError(f"User with email '{email}' already exists")

    pw_error = validate_password_strength(password)
    if pw_error:
        raise ValueError(pw_error)

    user = User(
        email=email,
        full_name=full_name,
        hashed_password=hash_password(password),
        role=role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


# Known weak/default passwords that must be rotated before production.
_WEAK_ADMIN_PASSWORDS = {
    "",
    "changeme",
    "changeme!",
    "changeme123",
    "changeme123!",
    "admin",
    "admin123",
    "admin123!",
    "password",
    "password123",
    "honeywell",
    "honeywell123",
}


def _check_admin_password_strength(password: str) -> None:
    """Emit CRITICAL log if admin password is weak or a known default.

    Intentionally non-blocking: we must allow dev/sandbox to boot even with a
    weak default, but the operator must see the warning in logs.
    """
    lowered = (password or "").strip().lower()
    if lowered in _WEAK_ADMIN_PASSWORDS or len(password) < 12:
        logger.critical(
            "SECURITY: DEFAULT_ADMIN_PASSWORD is weak or a known default — "
            "ROTATE IMMEDIATELY. Use: python3 -c 'import secrets;"
            "print(secrets.token_urlsafe(18))'"
        )


async def create_default_admin(db: AsyncSession) -> None:
    """Create the default admin user from settings if it does not already exist."""
    _check_admin_password_strength(settings.DEFAULT_ADMIN_PASSWORD)

    result = await db.execute(
        select(User).where(User.email == settings.DEFAULT_ADMIN_EMAIL)
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Do NOT overwrite password on restart — admin may have changed it via UI.
        # To force-reset: delete the admin from DB and restart, or use change-password API.
        logger.info("Default admin user already exists: %s", settings.DEFAULT_ADMIN_EMAIL)
        return

    admin = User(
        email=settings.DEFAULT_ADMIN_EMAIL,
        full_name="System Admin",
        hashed_password=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
        role="sales_manager",
        is_active=True,
        password_change_required=False,
    )
    db.add(admin)
    await db.commit()
    logger.info("Default admin user created: %s", settings.DEFAULT_ADMIN_EMAIL)
