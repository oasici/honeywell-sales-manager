from enum import Enum
from typing import Annotated

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import decode_token
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class Role(str, Enum):
    SALES_REP = "sales_rep"
    SALES_MANAGER = "sales_manager"
    OPERATIONS = "operations"


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    payload = decode_token(token)
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
