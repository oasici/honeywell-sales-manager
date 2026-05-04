"""Calendar integration service — Google Calendar + Microsoft Graph.

Provides OAuth2 flows, token management, event creation, sync, and linking to opportunities.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.setting import Setting

logger = logging.getLogger(__name__)

GOOGLE_AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_CALENDAR_BASE_URL = "https://www.googleapis.com/calendar/v3"

MICROSOFT_AUTH_BASE_URL = "https://login.microsoftonline.com"
MICROSOFT_TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
MICROSOFT_AUTH_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
MICROSOFT_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

TOKEN_EXPIRY_BUFFER_SECONDS = 300


# ── OAuth2 Flow Functions ──


# ── R4-AUTH-2 — signed OAuth state ──
#
# State must be unguessable AND tied to the originating user so a
# phished/replayed authorization code cannot be redeemed by anyone
# else. We HMAC the (provider, user_id, nonce, timestamp) tuple with
# the JWT secret; the callback re-derives the HMAC, checks freshness
# (10 min), and surfaces the signed user_id back to the caller for
# tenant scoping when persisting tokens.

_STATE_TTL_SECONDS = 600


def make_calendar_oauth_state(provider: str, user_id: int) -> str:
    """Mint a signed OAuth state for ``provider`` tied to ``user_id``."""
    import base64
    import hashlib
    import hmac
    import secrets
    import time as _time

    from app.core.config import settings as cfg

    nonce = secrets.token_urlsafe(16)
    ts = int(_time.time())
    payload = f"{provider}|{user_id}|{nonce}|{ts}"
    secret = (cfg.JWT_SECRET_KEY or "").encode() or b"unset"
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{payload}|{sig_b64}"


def verify_calendar_oauth_state(state: str) -> dict | None:
    """Return ``{provider, user_id}`` when ``state`` is valid + fresh."""
    import base64
    import hashlib
    import hmac
    import time as _time

    from app.core.config import settings as cfg

    if not state or state.count("|") != 4:
        return None
    provider, user_id_s, nonce, ts_s, sig_b64 = state.split("|")
    try:
        ts = int(ts_s)
        user_id = int(user_id_s)
    except ValueError:
        return None
    if _time.time() - ts > _STATE_TTL_SECONDS:
        return None
    secret = (cfg.JWT_SECRET_KEY or "").encode() or b"unset"
    expected = hmac.new(
        secret,
        f"{provider}|{user_id}|{nonce}|{ts}".encode(),
        hashlib.sha256,
    ).digest()
    expected_b64 = base64.urlsafe_b64encode(expected).rstrip(b"=").decode()
    if not hmac.compare_digest(expected_b64, sig_b64):
        return None
    return {"provider": provider, "user_id": user_id}


def get_google_auth_url(
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    state: str = "google",
) -> str:
    """Generate Google OAuth2 authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{GOOGLE_AUTH_BASE_URL}?{urlencode(params)}"


async def exchange_google_code(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> dict:
    """Exchange authorization code for tokens.

    Returns {access_token, refresh_token, expires_in, token_type}.
    """
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_in": data.get("expires_in", 3600),
            "token_type": data.get("token_type", "Bearer"),
        }


async def refresh_google_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict:
    """Refresh expired Google access token."""
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(GOOGLE_TOKEN_URL, data=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": refresh_token,
            "expires_in": data.get("expires_in", 3600),
            "token_type": data.get("token_type", "Bearer"),
        }


def get_microsoft_auth_url(
    tenant_id: str,
    client_id: str,
    redirect_uri: str,
    scopes: list[str],
    state: str = "microsoft",
) -> str:
    """Generate Microsoft OAuth2 authorization URL."""
    base = MICROSOFT_AUTH_URL_TEMPLATE.format(tenant_id=tenant_id)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "response_mode": "query",
        "state": state,
    }
    return f"{base}?{urlencode(params)}"


async def exchange_microsoft_code(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    scopes: list[str],
) -> dict:
    """Exchange Microsoft authorization code for tokens."""
    token_url = MICROSOFT_TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id)
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(token_url, data=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token"),
            "expires_in": data.get("expires_in", 3600),
            "token_type": data.get("token_type", "Bearer"),
        }


async def refresh_microsoft_token(
    tenant_id: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    scopes: list[str],
) -> dict:
    """Refresh expired Microsoft access token."""
    token_url = MICROSOFT_TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id)
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": " ".join(scopes),
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(token_url, data=payload)
        resp.raise_for_status()
        data = resp.json()
        return {
            "access_token": data["access_token"],
            "refresh_token": data.get("refresh_token", refresh_token),
            "expires_in": data.get("expires_in", 3600),
            "token_type": data.get("token_type", "Bearer"),
        }


# ── Token Storage Helpers ──

TOKENS_SETTING_KEY = "calendar_oauth_tokens"


async def _load_tokens(db: AsyncSession) -> dict | None:
    """Load stored OAuth tokens from the Setting model.

    Round-4 R4-PII-1: tokens are now Fernet-encrypted at rest. The
    decoder transparently handles legacy plaintext rows so the rollout
    doesn't lock anyone out — the next ``_save_tokens`` overwrites
    those rows with ciphertext.
    """
    from app.core.crypto import decrypt_json_or_legacy_plaintext

    result = await db.execute(
        select(Setting).where(Setting.key == TOKENS_SETTING_KEY)
    )
    setting = result.scalar_one_or_none()
    if not setting or not setting.value:
        return None
    decoded = decrypt_json_or_legacy_plaintext(setting.value)
    if decoded is None:
        logger.warning("Failed to read stored calendar tokens")
    return decoded


async def _save_tokens(db: AsyncSession, tokens: dict) -> None:
    """Save OAuth tokens to the Setting model (Fernet-encrypted, R4-PII-1)."""
    from app.core.crypto import encrypt_json

    tokens_with_timestamp = {
        **tokens,
        "saved_at": int(time.time()),
    }
    serialized = encrypt_json(tokens_with_timestamp)

    result = await db.execute(
        select(Setting).where(Setting.key == TOKENS_SETTING_KEY)
    )
    existing = result.scalar_one_or_none()
    if existing:
        existing.value = serialized
    else:
        db.add(Setting(key=TOKENS_SETTING_KEY, value=serialized))

    await db.flush()


class CalendarService:
    """Calendar integration with Google Calendar and Microsoft Graph."""

    def __init__(self, access_token: str, provider: str = "google"):
        self.access_token = access_token
        self.provider = provider
        self._headers = {"Authorization": f"Bearer {access_token}"}

    @classmethod
    async def from_db(cls, db: AsyncSession, provider: str) -> "CalendarService":
        """Create a CalendarService with a valid token from the database.

        Automatically refreshes the token if expired.
        """
        tokens = await _load_tokens(db)
        if not tokens:
            raise ValueError("Kaydedilmis takvim tokeni bulunamadi")

        access_token = await _ensure_valid_token(db, tokens, provider)
        return cls(access_token=access_token, provider=provider)

    async def create_event(
        self,
        *,
        title: str,
        start: datetime,
        end: datetime,
        description: str = "",
        attendees: list[str] | None = None,
        location: str = "",
    ) -> dict:
        """Create a calendar event and return the event data."""
        if self.provider == "google":
            return await self._create_google_event(
                title=title, start=start, end=end,
                description=description, attendees=attendees, location=location,
            )
        elif self.provider == "microsoft":
            return await self._create_microsoft_event(
                title=title, start=start, end=end,
                description=description, attendees=attendees, location=location,
            )
        else:
            raise ValueError(f"Desteklenmeyen takvim saglayicisi: {self.provider}")

    async def list_events(
        self,
        *,
        start: datetime,
        end: datetime,
        max_results: int = 50,
    ) -> list[dict]:
        """List calendar events in a date range."""
        if self.provider == "google":
            return await self._list_google_events(start=start, end=end, max_results=max_results)
        elif self.provider == "microsoft":
            return await self._list_microsoft_events(start=start, end=end, max_results=max_results)
        else:
            return []

    # ── Google Calendar ──

    async def _create_google_event(
        self, *, title, start, end, description, attendees, location
    ) -> dict:
        body = {
            "summary": title,
            "description": description,
            "location": location,
            "start": {"dateTime": start.isoformat(), "timeZone": "Europe/Istanbul"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Europe/Istanbul"},
        }
        if attendees:
            body["attendees"] = [{"email": e} for e in attendees]

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{GOOGLE_CALENDAR_BASE_URL}/calendars/primary/events",
                headers=self._headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("Google Calendar event created: %s", data.get("id"))
            return {
                "id": data["id"],
                "provider": "google",
                "title": data.get("summary"),
                "start": data.get("start", {}).get("dateTime"),
                "end": data.get("end", {}).get("dateTime"),
                "link": data.get("htmlLink"),
            }

    async def _list_google_events(self, *, start, end, max_results) -> list[dict]:
        params = {
            "timeMin": start.isoformat(),
            "timeMax": end.isoformat(),
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{GOOGLE_CALENDAR_BASE_URL}/calendars/primary/events",
                headers=self._headers,
                params=params,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            return [
                {
                    "id": e["id"],
                    "title": e.get("summary", ""),
                    "start": e.get("start", {}).get("dateTime"),
                    "end": e.get("end", {}).get("dateTime"),
                    "provider": "google",
                }
                for e in items
            ]

    # ── Microsoft Graph ──

    async def _create_microsoft_event(
        self, *, title, start, end, description, attendees, location
    ) -> dict:
        body = {
            "subject": title,
            "body": {"contentType": "text", "content": description},
            "start": {"dateTime": start.isoformat(), "timeZone": "Europe/Istanbul"},
            "end": {"dateTime": end.isoformat(), "timeZone": "Europe/Istanbul"},
        }
        if location:
            body["location"] = {"displayName": location}
        if attendees:
            body["attendees"] = [
                {"emailAddress": {"address": e}, "type": "required"} for e in attendees
            ]

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{MICROSOFT_GRAPH_BASE_URL}/me/events",
                headers=self._headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("Microsoft Calendar event created: %s", data.get("id"))
            return {
                "id": data["id"],
                "provider": "microsoft",
                "title": data.get("subject"),
                "start": data.get("start", {}).get("dateTime"),
                "end": data.get("end", {}).get("dateTime"),
                "link": data.get("webLink"),
            }

    async def _list_microsoft_events(self, *, start, end, max_results) -> list[dict]:
        params = {
            "$filter": f"start/dateTime ge '{start.isoformat()}' and end/dateTime le '{end.isoformat()}'",
            "$top": max_results,
            "$orderby": "start/dateTime",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{MICROSOFT_GRAPH_BASE_URL}/me/events",
                headers=self._headers,
                params=params,
            )
            resp.raise_for_status()
            items = resp.json().get("value", [])
            return [
                {
                    "id": e["id"],
                    "title": e.get("subject", ""),
                    "start": e.get("start", {}).get("dateTime"),
                    "end": e.get("end", {}).get("dateTime"),
                    "provider": "microsoft",
                }
                for e in items
            ]


async def _ensure_valid_token(
    db: AsyncSession,
    tokens: dict,
    provider: str,
) -> str:
    """Check if token is expired, refresh if needed, return valid token."""
    saved_at = tokens.get("saved_at", 0)
    expires_in = tokens.get("expires_in", 3600)
    is_expired = (time.time() - saved_at) >= (expires_in - TOKEN_EXPIRY_BUFFER_SECONDS)

    if not is_expired:
        return tokens["access_token"]

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        raise ValueError("Token suresi dolmus ve refresh_token mevcut degil")

    logger.info("Calendar token expired, refreshing for provider: %s", provider)

    if provider == "google":
        new_tokens = await refresh_google_token(
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            refresh_token=refresh_token,
        )
    elif provider == "microsoft":
        new_tokens = await refresh_microsoft_token(
            tenant_id=settings.AZURE_TENANT_ID,
            client_id=settings.AZURE_CLIENT_ID,
            client_secret=settings.AZURE_CLIENT_SECRET,
            refresh_token=refresh_token,
            scopes=["https://graph.microsoft.com/Calendars.ReadWrite", "offline_access"],
        )
    else:
        raise ValueError(f"Desteklenmeyen provider: {provider}")

    await _save_tokens(db, new_tokens)
    return new_tokens["access_token"]
