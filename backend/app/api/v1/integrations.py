"""v2 Integration hooks — calendar auto-link + e-sign contract.

These are interface/hook endpoints ready for external provider connection.
No paid API dependency — they define the contract and store configuration.
Actual provider calls are stubbed until credentials are configured.
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.enums import UserRole
from app.models.opportunity import Opportunity, OpportunityEvent
from app.models.setting import Setting
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["Integrations (v2)"])

# Supported providers
CALENDAR_PROVIDERS = {"google", "microsoft", "caldav"}
ESIGN_PROVIDERS = {"docusign", "hellosign", "yousign"}


# ══════════════════════════════════════════
# 1. CALENDAR — auto-link meetings to opportunity
# ══════════════════════════════════════════

GOOGLE_CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]
MICROSOFT_CALENDAR_SCOPES = [
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "offline_access",
]


@router.get("/calendar/auth-url")
async def get_calendar_auth_url(
    provider: str = "google",
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
):
    """Return the OAuth authorize URL for the specified calendar provider.

    The ``state`` is HMAC-signed (R4-AUTH-2) and tied to the requesting
    user so a phished/replayed authorization code cannot be redeemed
    by another session.
    """
    from app.services.calendar_service import (
        get_google_auth_url,
        get_microsoft_auth_url,
        make_calendar_oauth_state,
    )

    state = make_calendar_oauth_state(provider, current_user.id)

    if provider == "google":
        if not settings.GOOGLE_CLIENT_ID:
            raise BadRequestException("GOOGLE_CLIENT_ID yapilandirilmamis")
        url = get_google_auth_url(
            client_id=settings.GOOGLE_CLIENT_ID,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
            scopes=GOOGLE_CALENDAR_SCOPES,
            state=state,
        )
    elif provider == "microsoft":
        if not settings.AZURE_CLIENT_ID or not settings.AZURE_TENANT_ID:
            raise BadRequestException("Azure OAuth yapilandirmasi eksik")
        url = get_microsoft_auth_url(
            tenant_id=settings.AZURE_TENANT_ID,
            client_id=settings.AZURE_CLIENT_ID,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
            scopes=MICROSOFT_CALENDAR_SCOPES,
            state=state,
        )
    else:
        raise BadRequestException(
            f"Desteklenmeyen provider: {provider}. Desteklenen: google, microsoft"
        )

    return {"auth_url": url, "provider": provider}


@router.get("/calendar/callback")
async def calendar_oauth_callback(
    code: str,
    state: str = "google",
    db: AsyncSession = Depends(get_db),
):
    """Handle OAuth callback, exchange code for tokens, store them.

    R4-AUTH-2: ``state`` must be a signed token minted by
    ``/calendar/auth-url``. Legacy plain-string states (``"google"`` /
    ``"microsoft"``) are tolerated for one release so any in-flight
    OAuth dialogs from before the rollout still complete; new states
    sign the originating user_id which we use to scope token storage.
    """
    from app.services.calendar_service import (
        exchange_google_code,
        exchange_microsoft_code,
        _save_tokens,
        verify_calendar_oauth_state,
    )

    verified = verify_calendar_oauth_state(state)
    if verified is not None:
        provider = verified["provider"]
    elif state in {"google", "microsoft"}:
        # Backwards-compat for the rollout window. New auth-url calls
        # always emit signed states.
        provider = state
        logger.warning("calendar callback used legacy unsigned state=%s", state)
    else:
        raise BadRequestException("Gecersiz veya suresi dolmus state")

    if provider == "google":
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise BadRequestException("Google OAuth yapilandirmasi eksik")
        tokens = await exchange_google_code(
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
            code=code,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
        )
    elif provider == "microsoft":
        if not settings.AZURE_CLIENT_ID or not settings.AZURE_CLIENT_SECRET:
            raise BadRequestException("Microsoft OAuth yapilandirmasi eksik")
        tokens = await exchange_microsoft_code(
            tenant_id=settings.AZURE_TENANT_ID,
            client_id=settings.AZURE_CLIENT_ID,
            client_secret=settings.AZURE_CLIENT_SECRET,
            code=code,
            redirect_uri=settings.GOOGLE_REDIRECT_URI,
            scopes=MICROSOFT_CALENDAR_SCOPES,
        )
    else:
        raise BadRequestException(f"Bilinmeyen provider state: {state}")

    tokens["provider"] = provider
    await _save_tokens(db, tokens)

    # Also update the calendar_provider and legacy access_token settings
    provider_setting = (
        await db.execute(select(Setting).where(Setting.key == "calendar_provider"))
    ).scalar_one_or_none()
    if provider_setting:
        provider_setting.value = provider
    else:
        db.add(Setting(key="calendar_provider", value=provider))

    token_setting = (
        await db.execute(select(Setting).where(Setting.key == "calendar_access_token"))
    ).scalar_one_or_none()
    if token_setting:
        token_setting.value = tokens["access_token"]
    else:
        db.add(Setting(key="calendar_access_token", value=tokens["access_token"]))

    await db.flush()

    logger.info("Calendar OAuth completed for provider: %s", provider)

    return {
        "message": f"{provider} takvim baglantisi basariyla kuruldu",
        "provider": provider,
        "status": "connected",
    }


class CalendarConnectRequest(BaseModel):
    provider: str  # google | microsoft | caldav
    config: dict = {}  # provider-specific: client_id, redirect_uri, caldav_url, etc.


class CalendarEventLink(BaseModel):
    opportunity_id: int
    event_title: str
    event_date: str  # ISO datetime
    attendees: str | None = None  # comma-separated
    notes: str | None = None


@router.post("/calendar/connect")
async def connect_calendar(
    body: CalendarConnectRequest,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Configure calendar provider credentials.

    Hook: stores config in settings table. Actual OAuth flow is provider-specific
    and should be handled by frontend redirect + callback.
    """
    if body.provider not in CALENDAR_PROVIDERS:
        raise BadRequestException(
            f"Desteklenmeyen takvim saglayicisi: {body.provider}. "
            f"Desteklenen: {', '.join(sorted(CALENDAR_PROVIDERS))}"
        )

    config_key = f"calendar_{body.provider}_config"
    existing = (await db.execute(select(Setting).where(Setting.key == config_key))).scalar_one_or_none()
    if existing:
        existing.value = json.dumps(body.config)
    else:
        db.add(Setting(key=config_key, value=json.dumps(body.config)))

    # Store active provider
    provider_setting = (await db.execute(select(Setting).where(Setting.key == "calendar_provider"))).scalar_one_or_none()
    if provider_setting:
        provider_setting.value = body.provider
    else:
        db.add(Setting(key="calendar_provider", value=body.provider))

    await db.flush()

    logger.info("Calendar provider configured: %s by user %s", body.provider, current_user.id)

    return {
        "message": f"{body.provider} takvim baglantisi yapilandirildi",
        "provider": body.provider,
        "status": "configured",
        "next_step": "OAuth dogrulama icin provider'a yonlendirme yapilmali",
    }


@router.get("/calendar/status")
async def get_calendar_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check calendar integration status."""
    provider = (await db.execute(select(Setting).where(Setting.key == "calendar_provider"))).scalar_one_or_none()
    if not provider or not provider.value:
        return {"connected": False, "provider": None, "status": "not_configured", "token_present": False, "last_sync_at": None}

    config_key = f"calendar_{provider.value}_config"
    config = (await db.execute(select(Setting).where(Setting.key == config_key))).scalar_one_or_none()
    token_setting = (await db.execute(select(Setting).where(Setting.key == "calendar_access_token"))).scalar_one_or_none()
    last_sync = (await db.execute(select(Setting).where(Setting.key == "calendar_last_sync_at"))).scalar_one_or_none()

    return {
        "connected": bool(config and config.value),
        "provider": provider.value,
        "status": "connected" if (config and config.value) else "configured",
        "token_present": bool(token_setting and token_setting.value),
        "last_sync_at": last_sync.value if (last_sync and last_sync.value) else None,
    }


@router.post("/calendar/link-event")
async def link_calendar_event(
    body: CalendarEventLink,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Manually link a meeting/calendar event to an opportunity.

    Creates a timeline event. When calendar provider is connected,
    this can be automated via webhook/polling.
    """
    opp = (await db.execute(select(Opportunity).where(Opportunity.id == body.opportunity_id))).scalar_one_or_none()
    if not opp:
        raise NotFoundException("Firsat bulunamadi")

    event = OpportunityEvent(
        opportunity_id=opp.id,
        event_type="meeting",
        description=f"{body.event_title} ({body.event_date})"
                    + (f" - Katilimcilar: {body.attendees}" if body.attendees else "")
                    + (f"\nNotlar: {body.notes}" if body.notes else ""),
    )
    db.add(event)
    await db.flush()

    return {
        "message": "Toplanti firsata baglandi",
        "event_id": event.id,
        "opportunity_id": opp.id,
    }


@router.post("/calendar/sync")
async def sync_calendar(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Trigger calendar sync (stub — actual sync requires provider API).

    When connected, this endpoint would:
    1. Fetch recent calendar events from provider API
    2. Match attendee emails to customers
    3. Auto-link events to opportunities
    4. Create timeline entries
    """
    provider = (await db.execute(select(Setting).where(Setting.key == "calendar_provider"))).scalar_one_or_none()
    if not provider or not provider.value:
        return {
            "message": "Takvim saglayicisi yapilandirilmamis",
            "synced_count": 0,
            "status": "not_configured",
        }

    # Real calendar sync using CalendarService
    token_setting = (await db.execute(select(Setting).where(Setting.key == "calendar_access_token"))).scalar_one_or_none()
    if not token_setting or not token_setting.value:
        return {
            "message": "Takvim erisim tokeni bulunamadi — yeniden baglanti kurulmali",
            "synced_count": 0,
            "status": "token_missing",
        }

    try:
        from datetime import datetime, timedelta, timezone
        from app.services.calendar_service import CalendarService
        from app.models.customer import Customer

        cal = CalendarService(access_token=token_setting.value, provider=provider.value)
        now = datetime.now(timezone.utc)
        events = await cal.list_events(start=now - timedelta(days=7), end=now + timedelta(days=30))

        synced = 0
        for event in events:
            # Auto-link if attendee matches a customer email
            # This is a simplified implementation
            db.add(OpportunityEvent(
                opportunity_id=None,  # Will be linked later via attendee matching
                event_type="meeting",
                description=f"[Sync] {event.get('title', '')}",
            ))
            synced += 1

        await db.flush()
        # Track last successful sync
        last_sync_setting = (await db.execute(select(Setting).where(Setting.key == "calendar_last_sync_at"))).scalar_one_or_none()
        ts = now.isoformat()
        if last_sync_setting:
            last_sync_setting.value = ts
        else:
            db.add(Setting(key="calendar_last_sync_at", value=ts))
        await db.flush()
        return {
            "message": f"{provider.value} takvim senkronizasyonu tamamlandi",
            "synced_count": synced,
            "status": "synced",
            "provider": provider.value,
        }
    except Exception as exc:
        return {
            "message": f"Senkronizasyon hatasi: {str(exc)[:200]}",
            "synced_count": 0,
            "status": "error",
        }


@router.get("/calendar/health")
async def calendar_health(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Health check for calendar integration (safe, read-only)."""
    provider = (await db.execute(select(Setting).where(Setting.key == "calendar_provider"))).scalar_one_or_none()
    token = (await db.execute(select(Setting).where(Setting.key == "calendar_access_token"))).scalar_one_or_none()
    if not provider or not provider.value:
        return {"ok": False, "status": "not_configured", "provider": None}
    if not token or not token.value:
        return {"ok": False, "status": "token_missing", "provider": provider.value}

    try:
        from datetime import datetime, timedelta, timezone
        from app.services.calendar_service import CalendarService

        cal = CalendarService(access_token=token.value, provider=provider.value)
        now = datetime.now(timezone.utc)
        _ = await cal.list_events(start=now - timedelta(days=1), end=now + timedelta(days=1))
        return {"ok": True, "status": "ok", "provider": provider.value}
    except Exception as exc:
        return {"ok": False, "status": "error", "provider": provider.value, "error": str(exc)[:200]}


class CalendarCreateEventRequest(BaseModel):
    title: str
    start: str  # ISO datetime
    end: str  # ISO datetime
    description: str = ""
    attendees: list[str] = []
    location: str = ""
    opportunity_id: int | None = None


@router.post("/calendar/events")
async def create_calendar_event(
    body: CalendarCreateEventRequest,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a real calendar event via provider API and optionally link to opportunity."""
    provider = (await db.execute(select(Setting).where(Setting.key == "calendar_provider"))).scalar_one_or_none()
    token = (await db.execute(select(Setting).where(Setting.key == "calendar_access_token"))).scalar_one_or_none()

    if not provider or not provider.value or not token or not token.value:
        raise NotFoundException("Takvim saglayicisi yapilandirilmamis veya token eksik")

    from datetime import datetime as dt
    from app.services.calendar_service import CalendarService

    cal = CalendarService(access_token=token.value, provider=provider.value)
    event_data = await cal.create_event(
        title=body.title,
        start=dt.fromisoformat(body.start),
        end=dt.fromisoformat(body.end),
        description=body.description,
        attendees=body.attendees or None,
        location=body.location,
    )

    # Link to opportunity if specified
    if body.opportunity_id:
        opp_event = OpportunityEvent(
            opportunity_id=body.opportunity_id,
            event_type="meeting",
            description=f"{body.title} ({body.start[:10]})"
                        + (f" - Katilimcilar: {', '.join(body.attendees)}" if body.attendees else ""),
        )
        db.add(opp_event)
        await db.flush()
        event_data["opportunity_event_id"] = opp_event.id

    return event_data


# ══════════════════════════════════════════
# 2. E-SIGN — contract/signature integration
# ══════════════════════════════════════════

class EsignConnectRequest(BaseModel):
    provider: str  # docusign | hellosign | yousign
    config: dict = {}  # api_key, account_id, webhook_url, etc.


class EsignSendRequest(BaseModel):
    quote_id: int
    signer_email: str
    signer_name: str
    message: str | None = "Lutfen teklifi inceleyip imzalayiniz."


@router.post("/esign/connect")
async def connect_esign(
    body: EsignConnectRequest,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Configure e-signature provider credentials.

    Hook: stores config. Actual API auth is provider-specific.
    """
    if body.provider not in ESIGN_PROVIDERS:
        raise BadRequestException(
            f"Desteklenmeyen e-imza saglayicisi: {body.provider}. "
            f"Desteklenen: {', '.join(sorted(ESIGN_PROVIDERS))}"
        )

    # Round-4 R4-PII-2 — encrypt provider config (api_key, account_id)
    # at rest with Fernet so a read-only DB compromise doesn't expose
    # the credential. Backwards-compatible: legacy plaintext rows are
    # decoded by the same helper used to read.
    from app.core.crypto import encrypt_json
    config_key = f"esign_{body.provider}_config"
    existing = (await db.execute(select(Setting).where(Setting.key == config_key))).scalar_one_or_none()
    encrypted_payload = encrypt_json(body.config)
    if existing:
        existing.value = encrypted_payload
    else:
        db.add(Setting(key=config_key, value=encrypted_payload))

    provider_setting = (await db.execute(select(Setting).where(Setting.key == "esign_provider"))).scalar_one_or_none()
    if provider_setting:
        provider_setting.value = body.provider
    else:
        db.add(Setting(key="esign_provider", value=body.provider))

    await db.flush()

    logger.info("E-sign provider configured: %s by user %s", body.provider, current_user.id)

    return {
        "message": f"{body.provider} e-imza baglantisi yapilandirildi",
        "provider": body.provider,
        "status": "configured",
    }


@router.get("/esign/status")
async def get_esign_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check e-sign integration status."""
    provider = (await db.execute(select(Setting).where(Setting.key == "esign_provider"))).scalar_one_or_none()
    if not provider or not provider.value:
        return {"connected": False, "provider": None}

    config_key = f"esign_{provider.value}_config"
    config = (await db.execute(select(Setting).where(Setting.key == config_key))).scalar_one_or_none()

    return {
        "connected": bool(config and config.value),
        "provider": provider.value,
    }


@router.post("/esign/send")
async def send_for_signature(
    body: EsignSendRequest,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Send a quote PDF for e-signature (stub — actual send requires provider API).

    When connected, this endpoint would:
    1. Get quote PDF path
    2. Upload to e-sign provider
    3. Create signing request with signer details
    4. Return signing URL for redirect
    5. Track status via webhook callback
    """
    from app.models.quote import Quote

    quote = (await db.execute(select(Quote).where(Quote.id == body.quote_id))).scalar_one_or_none()
    if not quote:
        raise NotFoundException("Teklif bulunamadi")

    provider = (await db.execute(select(Setting).where(Setting.key == "esign_provider"))).scalar_one_or_none()
    if not provider or not provider.value:
        return {
            "message": "E-imza saglayicisi yapilandirilmamis",
            "status": "not_configured",
            "next_step": "Ayarlar > Entegrasyonlar > E-imza bagla",
        }

    # Stub: actual implementation would call provider API here
    return {
        "message": f"E-imza gonderimi henuz uygulanmadi — {provider.value} hook hazir",
        "status": "stub",
        "provider": provider.value,
        "quote_id": quote.id,
        "quote_number": quote.quote_number,
        "signer_email": body.signer_email,
        "pdf_available": bool(quote.pdf_path),
    }


@router.post("/esign/webhook")
async def esign_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Webhook endpoint for e-sign provider callbacks.

    R4-AUTH-1 / R4-WEBH-1: this endpoint must NOT require a JWT (the
    external provider has no session) and MUST verify a per-provider
    HMAC signature on the request body. Without verification, anyone
    could POST forged "signed!" callbacks and flip foreign quotes /
    contracts to a terminal state.

    Header: ``X-Esign-Signature: sha256=<hexdigest>``. Secret is
    loaded from the per-provider ``esign_<provider>_webhook_secret``
    Setting row.
    """
    import hashlib
    import hmac

    body_bytes = await request.body()

    provider_setting = (
        await db.execute(select(Setting).where(Setting.key == "esign_provider"))
    ).scalar_one_or_none()
    if not provider_setting or not provider_setting.value:
        # No provider configured = no callback expected. Polite 200 so
        # the provider's webhook health check doesn't alert.
        return {"status": "no_provider"}

    provider = provider_setting.value
    secret_setting = (
        await db.execute(
            select(Setting).where(
                Setting.key == f"esign_{provider}_webhook_secret"
            )
        )
    ).scalar_one_or_none()
    if not secret_setting or not secret_setting.value:
        logger.warning(
            "esign webhook received but no secret configured for provider=%s",
            provider,
        )
        raise HTTPException(status_code=401, detail="Webhook secret yapilandirilmamis")

    # HMAC verification — accept either ``sha256=<hex>`` or raw hex
    # so providers with different conventions (Docusign vs HelloSign)
    # work without per-provider parsers.
    incoming_sig = (
        request.headers.get("X-Esign-Signature")
        or request.headers.get("X-Hub-Signature-256")
        or ""
    )
    if incoming_sig.startswith("sha256="):
        incoming_sig = incoming_sig[len("sha256="):]
    expected = hmac.new(
        secret_setting.value.encode(),
        body_bytes,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, incoming_sig.lower()):
        raise HTTPException(status_code=401, detail="Imza dogrulanamadi")

    # Verified — actual status update logic still pending; for now we
    # return the verified payload back so the integration can roll
    # forward in pieces.
    try:
        payload = json.loads(body_bytes.decode() or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = {"raw": True}
    logger.info("esign webhook verified, provider=%s payload_keys=%s", provider, list(payload.keys()))
    return {"status": "verified", "provider": provider}
