from typing import Annotated, Optional

from fastapi import Cookie, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import decode_token_async
from app.models.enums import UserRole
from app.models.user import User

# auto_error=False so we can fall back to cookie if header is missing.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

# Cookie name used by /auth/login to set HttpOnly auth cookie.
ACCESS_TOKEN_COOKIE = "access_token"

# Backward-compatible alias so existing `from dependencies import Role` still works
Role = UserRole


def _extract_token(
    header_token: Optional[str],
    cookie_token: Optional[str],
) -> Optional[str]:
    """Prefer Authorization header (explicit), fall back to HttpOnly cookie.

    Header-based auth covers legacy clients during migration; cookie-based
    auth is the secure target for the SPA (XSS cannot read HttpOnly cookies).
    """
    if header_token:
        return header_token
    if cookie_token:
        return cookie_token
    return None


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    header_token: Annotated[Optional[str], Depends(oauth2_scheme)] = None,
    cookie_token: Annotated[Optional[str], Cookie(alias=ACCESS_TOKEN_COOKIE)] = None,
) -> User:
    token = _extract_token(header_token, cookie_token)
    if not token:
        raise UnauthorizedException()

    payload = await decode_token_async(token)
    if payload is None or payload.get("type") != "access":
        raise UnauthorizedException()

    user_id = payload.get("sub")
    if user_id is None:
        raise UnauthorizedException()

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise UnauthorizedException()

    return user


def require_role(*roles: Role):
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in [r.value for r in roles]:
            raise ForbiddenException(f"Role '{current_user.role}' does not have access")
        return current_user

    return role_checker
