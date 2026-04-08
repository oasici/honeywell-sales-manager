"""v2 Integration hooks — calendar auto-link + e-sign contract.

These are interface/hook endpoints ready for external provider connection.
No paid API dependency — they define the contract and store configuration.
Actual provider calls are stubbed until credentials are configured.
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
        return {"connected": False, "provider": None}

    config_key = f"calendar_{provider.value}_config"
    config = (await db.execute(select(Setting).where(Setting.key == config_key))).scalar_one_or_none()

    return {
        "connected": bool(config and config.value),
        "provider": provider.value,
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

    # Stub: actual implementation would call provider API here
    return {
        "message": f"{provider.value} takvim senkronizasyonu henuz uygulanmadi — hook hazir",
        "synced_count": 0,
        "status": "stub",
        "provider": provider.value,
    }


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

    config_key = f"esign_{body.provider}_config"
    existing = (await db.execute(select(Setting).where(Setting.key == config_key))).scalar_one_or_none()
    if existing:
        existing.value = json.dumps(body.config)
    else:
        db.add(Setting(key=config_key, value=json.dumps(body.config)))

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
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Webhook endpoint for e-sign provider callbacks (stub).

    When implemented, this would:
    1. Verify webhook signature
    2. Parse signing status (sent/viewed/signed/declined)
    3. Update quote status accordingly
    4. Create notification for quote owner
    """
    return {
        "message": "E-imza webhook endpoint hazir — provider callback URL olarak yapilandirilmali",
        "status": "stub",
    }
