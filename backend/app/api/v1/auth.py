from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.models.enums import UserRole
from app.core.exceptions import BadRequestException, UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    revoke_token,
    validate_password_strength,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenResponse, UserCreate, UserResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

# Import limiter from main app (attached to app.state)
from slowapi import Limiter
from slowapi.util import get_remote_address

_limiter = Limiter(key_func=get_remote_address)

class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


@router.post("/login", response_model=TokenResponse)
@_limiter.limit(settings.RATE_LIMIT_LOGIN)
async def login(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """OAuth2-compatible login with rate limiting."""
    user = await auth_service.authenticate(db, form_data.username, form_data.password)
    if user is None:
        raise UnauthorizedException("Invalid email or password")

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        password_change_required=user.password_change_required,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=UserResponse)
async def register_user(
    body: UserCreate,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(require_role(UserRole.SALES_MANAGER))],
):
    """Register a new user. Only sales_manager role can create users."""
    # Validate password strength
    pw_error = validate_password_strength(body.password)
    if pw_error:
        raise BadRequestException(pw_error)

    try:
        user = await auth_service.register(
            db,
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            role=body.role,
        )
    except ValueError as e:
        raise BadRequestException(str(e))

    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Return the current authenticated user's info."""
    return UserResponse.model_validate(current_user)


@router.post("/refresh", response_model=TokenResponse)
@_limiter.limit("10/minute")
async def refresh_token_endpoint(
    request: Request,
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Exchange a refresh token for new tokens. Old refresh token is revoked."""
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise UnauthorizedException("Invalid or expired refresh token")

    user_id = payload.get("sub")
    if user_id is None:
        raise UnauthorizedException("Invalid refresh token payload")

    from sqlalchemy import select
    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise UnauthorizedException("Kullanici bulunamadi veya aktif degil")

    # Revoke old refresh token (rotation)
    revoke_token(body.refresh_token)

    new_access = create_access_token(data={"sub": str(user.id)})
    new_refresh = create_refresh_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user=UserResponse.model_validate(user),
    )


@router.post("/logout")
async def logout(
    body: LogoutRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """Revoke refresh token on logout."""
    if body.refresh_token:
        revoke_token(body.refresh_token)
    return {"message": "Logged out successfully"}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/change-password")
@_limiter.limit("3/minute")
async def change_password(
    request: Request,
    body: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Change the current user's password."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise BadRequestException("Current password is incorrect")

    pw_error = validate_password_strength(body.new_password)
    if pw_error:
        raise BadRequestException(pw_error)

    current_user.hashed_password = hash_password(body.new_password)
    current_user.password_change_required = False
    await db.flush()

    return {"message": "Password changed successfully"}
