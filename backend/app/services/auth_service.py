from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import hash_password, verify_password, validate_password_strength
from app.models.user import User

logger = logging.getLogger(__name__)


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    """Authenticate a user by email and password. Returns the User or None."""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()

    if user is None:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None

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
        logger.info("Default admin user already exists: %s", settings.DEFAULT_ADMIN_EMAIL)
        return

    admin = User(
        email=settings.DEFAULT_ADMIN_EMAIL,
        full_name="System Admin",
        hashed_password=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
        role="sales_manager",
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    logger.info("Default admin user created: %s", settings.DEFAULT_ADMIN_EMAIL)
