from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user_session import UserSession

logger = logging.getLogger(__name__)


async def create_session(
    db: AsyncSession,
    user_id: int,
    jti: str,
    device_info: str | None,
    ip_address: str | None,
    expires_at: datetime,
) -> UserSession:
    """Create a session. If active count exceeds MAX_CONCURRENT_SESSIONS, invalidate oldest."""
    max_sessions = settings.MAX_CONCURRENT_SESSIONS

    # Get active sessions ordered by creation time
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.is_active.is_(True),
        )
        .order_by(UserSession.created_at.asc())
    )
    active_sessions = list(result.scalars().all())

    # Invalidate oldest sessions if at or over limit
    while len(active_sessions) >= max_sessions:
        oldest = active_sessions.pop(0)
        oldest.is_active = False
        logger.info(
            "Oturum limiti asildi, eski oturum kapatildi: user_id=%d, jti=%s",
            user_id,
            oldest.jti,
        )

    session = UserSession(
        user_id=user_id,
        jti=jti,
        device_info=device_info,
        ip_address=ip_address,
        is_active=True,
        expires_at=expires_at,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def invalidate_session(db: AsyncSession, jti: str) -> bool:
    """Mark a session inactive by JTI. Returns True if found and deactivated."""
    result = await db.execute(
        select(UserSession).where(
            UserSession.jti == jti,
            UserSession.is_active.is_(True),
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        return False

    session.is_active = False
    await db.flush()
    return True


async def get_active_sessions(db: AsyncSession, user_id: int) -> list[UserSession]:
    """List active, non-expired sessions for a user."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == user_id,
            UserSession.is_active.is_(True),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.created_at.desc())
    )
    return list(result.scalars().all())


async def cleanup_expired(db: AsyncSession) -> int:
    """Remove expired sessions. Returns count of deleted rows."""
    now = datetime.now(timezone.utc)
    result = await db.execute(
        delete(UserSession).where(UserSession.expires_at <= now)
    )
    await db.flush()
    count = result.rowcount
    if count > 0:
        logger.info("Suresi dolmus %d oturum temizlendi", count)
    return count
