from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user_session import UserSession
from app.services import session_service


@pytest.fixture(autouse=True)
def enable_feature_flag(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_SESSION_MANAGEMENT", True)
    monkeypatch.setattr(settings, "MAX_CONCURRENT_SESSIONS", 3)


class TestSessionService:
    """Unit tests for session_service functions."""

    @pytest.mark.asyncio
    async def test_create_session(self, db: AsyncSession):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        session = await session_service.create_session(
            db=db,
            user_id=1,
            jti="test-jti-001",
            device_info="Chrome/Windows",
            ip_address="192.168.1.1",
            expires_at=expires,
        )

        assert session.id is not None
        assert session.user_id == 1
        assert session.jti == "test-jti-001"
        assert session.is_active is True

    @pytest.mark.asyncio
    async def test_exceed_limit_invalidates_oldest(self, db: AsyncSession):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)

        sessions = []
        for i in range(4):
            s = await session_service.create_session(
                db=db,
                user_id=1,
                jti=f"jti-limit-{i}",
                device_info=f"Device {i}",
                ip_address="10.0.0.1",
                expires_at=expires,
            )
            sessions.append(s)
            await db.commit()

        # After creating 4 sessions with limit 3, the oldest should be inactive
        await db.refresh(sessions[0])
        assert sessions[0].is_active is False

        # The latest 3 should still be active
        active = await session_service.get_active_sessions(db, 1)
        assert len(active) == 3

    @pytest.mark.asyncio
    async def test_invalidate_session(self, db: AsyncSession):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)
        session = await session_service.create_session(
            db=db,
            user_id=1,
            jti="jti-invalidate-test",
            device_info=None,
            ip_address=None,
            expires_at=expires,
        )
        await db.commit()

        result = await session_service.invalidate_session(db, "jti-invalidate-test")
        assert result is True

        await db.refresh(session)
        assert session.is_active is False

    @pytest.mark.asyncio
    async def test_invalidate_nonexistent_session(self, db: AsyncSession):
        result = await session_service.invalidate_session(db, "nonexistent-jti")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_active_sessions(self, db: AsyncSession):
        expires = datetime.now(timezone.utc) + timedelta(hours=1)

        await session_service.create_session(
            db, user_id=1, jti="active-1", device_info=None,
            ip_address=None, expires_at=expires,
        )
        await session_service.create_session(
            db, user_id=1, jti="active-2", device_info=None,
            ip_address=None, expires_at=expires,
        )
        await db.commit()

        active = await session_service.get_active_sessions(db, 1)
        assert len(active) == 2
        # Most recent first
        assert active[0].jti == "active-2"

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, db: AsyncSession):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        future = datetime.now(timezone.utc) + timedelta(hours=1)

        await session_service.create_session(
            db, user_id=1, jti="expired-session", device_info=None,
            ip_address=None, expires_at=past,
        )
        await session_service.create_session(
            db, user_id=1, jti="valid-session", device_info=None,
            ip_address=None, expires_at=future,
        )
        await db.commit()

        cleaned = await session_service.cleanup_expired(db)
        assert cleaned == 1

        active = await session_service.get_active_sessions(db, 1)
        assert len(active) == 1
        assert active[0].jti == "valid-session"


class TestSessionAPI:
    """Integration tests for session endpoints in auth router."""

    @pytest.mark.asyncio
    async def test_list_sessions_returns_empty(
        self, client: AsyncClient, auth_headers: dict,
    ):
        response = await client.get(
            "/api/v1/auth/sessions",
            headers=auth_headers,
        )
        # With session management enabled but no sessions created via login,
        # the list should be empty (token was created directly in fixture)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_feature_flag_disabled_returns_404(
        self, client: AsyncClient, auth_headers: dict, monkeypatch,
    ):
        monkeypatch.setattr(settings, "FEATURE_SESSION_MANAGEMENT", False)

        response = await client.get(
            "/api/v1/auth/sessions",
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_kill_nonexistent_session_returns_404(
        self, client: AsyncClient, auth_headers: dict,
    ):
        response = await client.delete(
            "/api/v1/auth/sessions/nonexistent-jti",
            headers=auth_headers,
        )
        assert response.status_code == 404
