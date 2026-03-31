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
    # Check lockout
    locked, remaining = _is_locked_out(email)
    if locked:
        logger.warning("Locked out login attempt for %s (%ds remaining)", email, remaining)
        return None

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        _record_failed_attempt(email)
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
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


async def create_default_admin(db: AsyncSession) -> None:
    """Create the default admin user from settings if it does not already exist."""
    result = await db.execute(
        select(User).where(User.email == settings.DEFAULT_ADMIN_EMAIL)
    )
    existing = result.scalar_one_or_none()

    if existing is not None:
        # Sync password with env variable on every startup
        if not verify_password(settings.DEFAULT_ADMIN_PASSWORD, existing.hashed_password):
            existing.hashed_password = hash_password(settings.DEFAULT_ADMIN_PASSWORD)
            await db.commit()
            logger.info("Default admin password updated from env: %s", settings.DEFAULT_ADMIN_EMAIL)
        else:
            logger.info("Default admin user already exists: %s", settings.DEFAULT_ADMIN_EMAIL)
        return

    admin = User(
        email=settings.DEFAULT_ADMIN_EMAIL,
        full_name="System Admin",
        hashed_password=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
        role="sales_manager",
        is_active=True,
        password_change_required=True,
    )
    db.add(admin)
    await db.commit()
    logger.info("Default admin user created: %s", settings.DEFAULT_ADMIN_EMAIL)
