from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession


from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.rate_limit import (
    enforce_login_rate_limit,
    enforce_login_username_rate_limit,
)
from app.models.enums import UserRole
from app.core.exceptions import BadRequestException, NotFoundException, UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token_async,
    hash_password,
    revoke_token_async,
    validate_password_strength,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import TokenResponse, UserCreate, UserResponse
from app.services import auth_service
from app.services import session_service
from app.schemas.common import MessageResponse

router = APIRouter(prefix="/auth", tags=["auth"])

class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


def _set_auth_cookies(
    response: Response,
    access_token: str,
    refresh_token: str,
) -> None:
    """Set HttpOnly auth cookies + a readable CSRF token cookie.

    - access_token: HttpOnly, Secure, SameSite=Lax (XSS cannot read it)
    - refresh_token: HttpOnly, Secure, SameSite=Strict, scoped to /auth
    - csrf_token: readable by JS (double-submit cookie pattern)
    """
    from app.core.security import generate_csrf_token

    # Access cookie — 30 min (ACCESS_TOKEN_EXPIRE_MINUTES)
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=True,
        secure=not settings.is_development,  # require HTTPS outside local dev
        samesite="lax",
        path="/",
    )
    # Refresh cookie — 7 days, scoped so only /auth/* sees it
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        max_age=7 * 24 * 60 * 60,
        httponly=True,
        secure=not settings.is_development,
        samesite="strict",
        path="/api/v1/auth",
    )
    # CSRF token — NOT HttpOnly (JS must read to echo in X-CSRF-Token header)
    response.set_cookie(
        key="csrf_token",
        value=generate_csrf_token(),
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        httponly=False,
        secure=not settings.is_development,
        samesite="strict",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    for name, path in (
        ("access_token", "/"),
        ("refresh_token", "/api/v1/auth"),
        ("csrf_token", "/"),
    ):
        response.delete_cookie(key=name, path=path)


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(enforce_login_rate_limit)],
)
async def login(
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """OAuth2-compatible login with strict rate limit to prevent brute-force.

    Issues both:
    - Response body tokens (for API clients / legacy SPAs)
    - HttpOnly cookies (preferred for browser SPA; resistant to XSS token theft)
    Frontend should progressively switch to cookie-based auth.
    """
    # Round-4 R4-RL-6 — per-username layer above the per-IP one.
    # A botnet rotating IPs can defeat the per-IP cap; the per-username
    # cap stops them at the same login target.
    enforce_login_username_rate_limit(form_data.username)

    # D-006 — persistent per-account lockout. The in-memory check above
    # disappears on process restart; this layer survives.
    from app.services.login_rate_limiter import (
        is_locked, record_failure, record_success,
    )
    if await is_locked(db, form_data.username):
        raise UnauthorizedException(
            "Hesabiniz 15 dakika kilitlendi. Lutfen daha sonra deneyin."
        )

    user = await auth_service.authenticate(db, form_data.username, form_data.password)
    if user is None:
        # Persist the failure. Increments counter + flips locked_until
        # at threshold. Even cross-restart-resilient.
        try:
            await record_failure(db, form_data.username)
            await db.commit()
        except Exception:
            await db.rollback()
        raise UnauthorizedException("Gecersiz e-posta veya sifre")

    # Successful auth — clear the persistent counter.
    try:
        await record_success(db, form_data.username)
        await db.commit()
    except Exception:
        await db.rollback()

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    # Create session if session management is enabled
    if settings.FEATURE_SESSION_MANAGEMENT:
        from datetime import timedelta, timezone
        from datetime import datetime

        access_payload = await decode_token_async(access_token)
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

    # Set secure cookies alongside JSON response (hybrid during migration)
    _set_auth_cookies(response, access_token, refresh_token)

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
    request: Request,
    body: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Exchange a refresh token for new tokens. Old refresh token is revoked."""
    refresh_token = body.refresh_token or request.cookies.get("refresh_token")
    if not refresh_token:
        raise UnauthorizedException("Yenileme tokeni eksik")

    # Async decode so multi-worker Redis revocation check is honoured
    # without spawning a nested event loop.
    payload = await decode_token_async(refresh_token)
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

    # Revoke old refresh token (rotation). Async variant writes to Redis so
    # sibling workers see the revocation immediately.
    await revoke_token_async(refresh_token)

    new_access = create_access_token(data={"sub": str(user.id)})
    new_refresh = create_refresh_token(data={"sub": str(user.id)})

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        user=UserResponse.model_validate(user),
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    body: LogoutRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """Revoke tokens and clear auth cookies on logout."""
    # Revoke access token from Authorization header OR cookie
    token_to_revoke = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token_to_revoke = auth_header[7:]
    elif request.cookies.get("access_token"):
        token_to_revoke = request.cookies["access_token"]

    if token_to_revoke:
        await revoke_token_async(token_to_revoke)
        if settings.FEATURE_SESSION_MANAGEMENT:
            payload = await decode_token_async(token_to_revoke)
            if payload and payload.get("jti"):
                await session_service.invalidate_session(db, payload["jti"])

    # Revoke refresh token if provided via body or cookie
    refresh = body.refresh_token or request.cookies.get("refresh_token")
    if refresh:
        await revoke_token_async(refresh)

    # Clear all auth cookies regardless of how token was supplied
    _clear_auth_cookies(response)

    return {"message": "Basariyla cikis yapildi"}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8, max_length=128)


@router.post(
    "/change-password",
    dependencies=[Depends(enforce_login_rate_limit)],
    response_model=MessageResponse,
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


@router.delete("/sessions/{jti}", response_model=MessageResponse)
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
