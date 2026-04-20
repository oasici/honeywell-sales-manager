from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.rate_limit import enforce_login_rate_limit
from app.models.enums import UserRole
from app.core.exceptions import BadRequestException, NotFoundException, UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    revoke_token,
    revoke_token_async,
    validate_password_strength,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenResponse, UserCreate, UserResponse
from app.services import auth_service
from app.services import session_service

router = APIRouter(prefix="/auth", tags=["auth"])

class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def login(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """OAuth2-compatible login with strict rate limit to prevent brute-force."""
    user = await auth_service.authenticate(db, form_data.username, form_data.password)
    if user is None:
        raise UnauthorizedException("Gecersiz e-posta veya sifre")

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    # Create session if session management is enabled
    if settings.FEATURE_SESSION_MANAGEMENT:
        from datetime import timedelta, timezone
        from datetime import datetime

        access_payload = decode_token(access_token)
        if access_payload and access_payload.get("jti"):
            device_info = form_data.scopes[0] if form_data.scopes else None
            ip_address = None
            expires_at = datetime.now(timezone.utc) + timedelta(
                minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
            )
            await session_service.create_session(
                db=db,
                user_id=user.id,
                jti=access_payload["jti"],
                device_info=device_info,
                ip_address=ip_address,
                expires_at=expires_at,
            )

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


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def refresh_token_endpoint(
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Exchange a refresh token for new tokens. Old refresh token is revoked."""
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise UnauthorizedException("Gecersiz veya suresi dolmus yenileme tokeni")

    user_id = payload.get("sub")
    if user_id is None:
        raise UnauthorizedException("Gecersiz yenileme tokeni icerigi")

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
    request: Request,
    body: LogoutRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """Revoke both access and refresh tokens on logout."""
    # Revoke access token from Authorization header
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        access_token = auth_header[7:]
        await revoke_token_async(access_token)

        # Invalidate session if session management is enabled
        if settings.FEATURE_SESSION_MANAGEMENT:
            payload = decode_token(access_token)
            if payload and payload.get("jti"):
                await session_service.invalidate_session(db, payload["jti"])

    # Revoke refresh token if provided
    if body.refresh_token:
        await revoke_token_async(body.refresh_token)
    return {"message": "Basariyla cikis yapildi"}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


@router.post(
    "/change-password",
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def change_password(
    body: ChangePasswordRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Change the current user's password."""
    if not verify_password(body.current_password, current_user.hashed_password):
        raise BadRequestException("Mevcut sifre yanlis")

    pw_error = validate_password_strength(body.new_password)
    if pw_error:
        raise BadRequestException(pw_error)

    current_user.hashed_password = hash_password(body.new_password)
    current_user.password_change_required = False
    await db.flush()

    return {"message": "Sifre basariyla degistirildi"}


class SessionResponse(BaseModel):
    id: int
    jti: str
    device_info: str | None = None
    ip_address: str | None = None
    is_active: bool
    created_at: str | None = None
    expires_at: str | None = None


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Aktif oturumlari listele."""
    if not settings.FEATURE_SESSION_MANAGEMENT:
        raise NotFoundException("Bu ozellik aktif degil")

    sessions = await session_service.get_active_sessions(db, current_user.id)
    return [
        SessionResponse(
            id=s.id,
            jti=s.jti,
            device_info=s.device_info,
            ip_address=s.ip_address,
            is_active=s.is_active,
            created_at=s.created_at.isoformat() if s.created_at else None,
            expires_at=s.expires_at.isoformat() if s.expires_at else None,
        )
        for s in sessions
    ]


@router.delete("/sessions/{jti}")
async def kill_session(
    jti: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Belirli bir oturumu sonlandir."""
    if not settings.FEATURE_SESSION_MANAGEMENT:
        raise NotFoundException("Bu ozellik aktif degil")

    deleted = await session_service.invalidate_session(db, jti)
    if not deleted:
        raise NotFoundException("Oturum bulunamadi veya zaten kapatilmis")

    return {"message": "Oturum basariyla sonlandirildi"}
