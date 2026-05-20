from __future__ import annotations

import os
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.api_key import ApiKey
from app.models.enums import UserRole
from app.models.setting import Setting
from app.models.stage_config import StageConfig
from app.models.user import User
from app.schemas.setting import (
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyRevokeResponse,
    EmailCredentialsReadResponse,
    EmailCredentialsSaveResponse,
    EmailTestResponse,
    NotificationChannelsResponse,
    NotificationChannelsTestResponse,
    SettingsMapResponse,
    SettingsUpdateResponse,
    StageConfigListResponse,
    StageConfigUpdateResponse,
    SystemConfigResponse,
    SystemConfigUpdateResponse,
)

router = APIRouter(prefix="/settings", tags=["Settings"])


# ── Password encryption helpers ──

_KEY_FILE = os.path.join("data", ".encryption_key")


def _get_fernet():
    from app.core.config import settings as cfg

    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key:
        if cfg.is_production:
            raise RuntimeError(
                "ENCRYPTION_KEY must be set in production. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        # Development/test: persist to file so all workers + restarts share the same key
        if os.path.exists(_KEY_FILE):
            with open(_KEY_FILE) as f:
                key = f.read().strip()
        if not key:
            key = Fernet.generate_key().decode()
            os.makedirs(os.path.dirname(_KEY_FILE), exist_ok=True)
            with open(_KEY_FILE, "w") as f:
                f.write(key)
        os.environ["ENCRYPTION_KEY"] = key
    return Fernet(key.encode() if isinstance(key, str) else key)


def _encrypt_password(password: str) -> str:
    return _get_fernet().encrypt(password.encode()).decode()


def _decrypt_password(encrypted: str) -> str:
    return _get_fernet().decrypt(encrypted.encode()).decode()


# ── Pydantic schemas ──

# Known email provider IMAP/SMTP settings
_PROVIDER_MAP = {
    "gmail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 587),
    "googlemail.com": ("imap.gmail.com", 993, "smtp.gmail.com", 587),
    "yahoo.com": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587),
    "yahoo.com.tr": ("imap.mail.yahoo.com", 993, "smtp.mail.yahoo.com", 587),
    "outlook.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "hotmail.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "live.com": ("outlook.office365.com", 993, "smtp.office365.com", 587),
    "yandex.com": ("imap.yandex.com", 993, "smtp.yandex.com", 587),
    "icloud.com": ("imap.mail.me.com", 993, "smtp.mail.me.com", 587),
}


def _detect_provider(email: str) -> tuple[str, int, str, int]:
    """Auto-detect IMAP/SMTP settings from email domain."""
    domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    if domain in _PROVIDER_MAP:
        return _PROVIDER_MAP[domain]
    # Default to Outlook/O365 for corporate domains
    return "outlook.office365.com", 993, "smtp.office365.com", 587


class SettingsUpdateRequest(BaseModel):
    quote_prefix: str | None = None
    default_tax_rate: float | None = None
    default_currency: str | None = None
    quote_validity_days: int | None = None


class EmailCredentials(BaseModel):
    email_address: str
    email_password: str
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587


# ── Settings CRUD ──

# R5-PII-4 — keys whose values are secrets and must never round-trip
# in cleartext through GET /settings/. Substring match so "esign_*_
# webhook_secret", "*_api_key", "*_token" are all caught. Intentionally
# broad: false-positive masks a non-secret value (annoyance), false
# negative leaks a secret (incident).
_SENSITIVE_SUBSTRINGS = (
    "password",
    "secret",
    "_token",
    "api_key",
    "_key",
    "private",
)


def _is_sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(s in k for s in _SENSITIVE_SUBSTRINGS)


def _mask_settings(settings_dict: dict[str, str | None]) -> dict[str, str | None]:
    """Replace sensitive values with the canonical mask sentinel.

    Preserves NULL → NULL so the SPA can tell "not configured" from
    "configured but masked".
    """
    return {
        k: ("********" if (_is_sensitive_key(k) and v is not None) else v)
        for k, v in settings_dict.items()
    }


@router.get("/", response_model=SettingsMapResponse)
async def get_settings(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Get all settings as a key-value map (sales_manager only).

    R5-PII-4 — every key matching ``_SENSITIVE_SUBSTRINGS`` is masked
    in the response. Pre-R5 this was only ``email_password``; the
    esign provider webhook secret and any other DB-stored credential
    leaked in cleartext.
    """
    result = await db.execute(select(Setting).order_by(Setting.key))
    settings = result.scalars().all()
    settings_dict = {s.key: s.value for s in settings}
    return {"settings": _mask_settings(settings_dict)}


@router.put("/", response_model=SettingsUpdateResponse)
async def update_settings(
    data: SettingsUpdateRequest,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update settings from a validated request body.

    R5-PII-5 — values for keys matching ``_SENSITIVE_SUBSTRINGS`` are
    encrypted at rest with Fernet. Read sites in this module use
    ``decrypt_str_or_legacy_plaintext`` so values written before
    encryption was wired (legacy plaintext) keep working.
    """
    from app.core.crypto import encrypt_str

    updated_keys = []

    for key, value in data.model_dump(exclude_none=True).items():

        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()

        # Skip the literal mask sentinel — the SPA echoes "********"
        # back when the user didn't change a sensitive field; persisting
        # that would brick the secret.
        if value == "********":
            continue

        stored_value: str | None
        if value is None:
            stored_value = None
        else:
            raw = str(value)
            stored_value = encrypt_str(raw) if _is_sensitive_key(key) else raw

        if setting:
            setting.value = stored_value
        else:
            setting = Setting(key=key, value=stored_value)
            db.add(setting)

        updated_keys.append(key)

    await db.flush()

    all_result = await db.execute(select(Setting).order_by(Setting.key))
    all_settings = all_result.scalars().all()
    settings_dict = {s.key: s.value for s in all_settings}

    return {
        "message": f"Updated {len(updated_keys)} setting(s)",
        "updated_keys": updated_keys,
        "settings": _mask_settings(settings_dict),
    }


# ── Email Credentials ──

@router.post("/email-credentials", response_model=EmailCredentialsSaveResponse)
async def save_email_credentials(
    body: EmailCredentials,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Save email credentials and mark user's email setup as completed."""
    if not body.email_address or not body.email_password:
        raise BadRequestException("Email adresi ve sifre gereklidir")

    # Auto-detect provider from email domain
    detected_imap, detected_imap_port, detected_smtp, detected_smtp_port = _detect_provider(body.email_address)

    # Use detected values if user didn't explicitly set custom ones
    default_hosts = {"", "outlook.office365.com", "smtp.office365.com"}
    if not body.imap_host or body.imap_host in default_hosts:
        body.imap_host = detected_imap
        body.imap_port = detected_imap_port
    if not body.smtp_host or body.smtp_host in default_hosts:
        body.smtp_host = detected_smtp
        body.smtp_port = detected_smtp_port

    # If password is placeholder, keep existing encrypted value
    password_value = body.email_password
    if password_value == "___KEEP_EXISTING___":
        existing_pw = await db.execute(select(Setting).where(Setting.key == "email_password"))
        pw_setting = existing_pw.scalar_one_or_none()
        if pw_setting:
            # Already stored encrypted; keep as-is
            password_value = pw_setting.value or ""
        else:
            password_value = ""
    else:
        # Encrypt before storing
        password_value = _encrypt_password(password_value)

    cred_map = {
        "email_address": body.email_address,
        "email_password": password_value,
        "imap_host": body.imap_host,
        "imap_port": str(body.imap_port),
        "smtp_host": body.smtp_host,
        "smtp_port": str(body.smtp_port),
    }

    for key, value in cred_map.items():
        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            db.add(Setting(key=key, value=value))

    # Mark user's email setup as completed
    current_user.email_setup_completed = True

    await db.flush()

    return {"message": "Email bilgileri kaydedildi", "email_setup_completed": True}


@router.get("/email-credentials", response_model=EmailCredentialsReadResponse)
async def get_email_credentials(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get email credentials (password masked)."""
    keys = ["email_address", "email_password", "imap_host", "imap_port", "smtp_host", "smtp_port"]
    result = await db.execute(select(Setting).where(Setting.key.in_(keys)))
    settings = {s.key: s.value for s in result.scalars().all()}

    return {
        "email_address": settings.get("email_address", ""),
        "email_password": "********" if settings.get("email_password") else "",
        "imap_host": settings.get("imap_host", "outlook.office365.com"),
        "imap_port": int(settings.get("imap_port", "993")),
        "smtp_host": settings.get("smtp_host", "smtp.office365.com"),
        "smtp_port": int(settings.get("smtp_port", "587")),
        "is_configured": bool(settings.get("email_address")),
    }


class EmailTestRequest(BaseModel):
    email_address: str = ""
    email_password: str = ""
    imap_host: str = ""
    imap_port: int = 993


@router.post("/email-credentials/test", response_model=EmailTestResponse)
async def test_email_connection(
    body: EmailTestRequest | None = None,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Test email IMAP connection. Accepts credentials directly or uses stored ones."""

    email_addr = ""
    email_pass = ""
    imap_host = ""
    imap_port = 993

    if body and body.email_address and body.email_password:
        # Use provided credentials directly (no save needed)
        email_addr = body.email_address
        email_pass = body.email_password
        imap_host = body.imap_host
        imap_port = body.imap_port
    else:
        # Fall back to stored credentials (password is encrypted)
        result = await db.execute(
            select(Setting).where(
                Setting.key.in_(["email_address", "email_password", "imap_host", "imap_port"])
            )
        )
        stored = {s.key: s.value for s in result.scalars().all()}
        email_addr = stored.get("email_address", "")
        encrypted_pass = stored.get("email_password", "")
        email_pass = _decrypt_password(encrypted_pass) if encrypted_pass else ""
        imap_host = stored.get("imap_host", "")
        imap_port = int(stored.get("imap_port", "993"))

    if not email_addr or not email_pass:
        raise BadRequestException("Email bilgileri gereklidir")

    # Auto-detect provider or validate custom host against whitelist (SSRF prevention)
    detected_h, detected_p, _, _ = _detect_provider(email_addr)
    _allowed_imap_hosts = {v[0] for v in _PROVIDER_MAP.values()}  # known provider hosts
    default_hosts = {"", "outlook.office365.com"}
    if not imap_host or imap_host in default_hosts:
        imap_host = detected_h
        imap_port = detected_p
    elif imap_host not in _allowed_imap_hosts:
        import logging as _ssrf_log
        _ssrf_log.getLogger(__name__).warning(
            "SSRF guard: custom IMAP host '%s' attempted by user %s",
            imap_host, current_user.id,
        )
        raise BadRequestException(
            f"Desteklenmeyen IMAP sunucusu: {imap_host}. "
            "Desteklenen: Gmail, Yahoo, Outlook, Yandex, iCloud."
        )

    try:
        import imaplib
        imap = imaplib.IMAP4_SSL(imap_host, imap_port)
        imap.login(email_addr, email_pass)
        status, messages = imap.select("INBOX", readonly=True)
        msg_count = int(messages[0]) if status == "OK" else 0
        imap.logout()

        return {
            "success": True,
            "message": f"Baglanti basarili! ({imap_host}) Gelen kutusunda {msg_count} email bulundu.",
            "imap_host": imap_host,
            "imap_port": imap_port,
        }
    except imaplib.IMAP4.error as e:
        return {
            "success": False,
            "message": f"Giris basarisiz ({imap_host}): {str(e)}",
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Baglanti hatasi ({imap_host}:{imap_port}): {str(e)}",
        }


# ── API Key Management ──


class ApiKeyCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    scopes_json: str | None = None
    rate_limit: int = Field(default=1000, ge=1, le=100000)


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_api_keys(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """List user's API keys (manager only). Key hashes are never returned."""
    from app.core.config import settings as cfg

    if not cfg.FEATURE_PUBLIC_API:
        raise HTTPException(status_code=404, detail="Not found")

    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == current_user.id)
        .order_by(ApiKey.created_at.desc())
    )
    keys = result.scalars().all()
    items = [
        {
            "id": k.id,
            "name": k.name,
            "scopes_json": k.scopes_json,
            "rate_limit": k.rate_limit,
            "is_active": k.is_active,
            "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            "created_at": k.created_at.isoformat() if k.created_at else None,
        }
        for k in keys
    ]
    # Round-13 R13-API-1 — full canonical envelope.
    return {
        "items": items,
        "total": len(items),
        "page": 1,
        "page_size": len(items) if items else 0,
        "pages": 1 if items else 0,
    }


@router.post("/api-keys", status_code=201, response_model=ApiKeyCreateResponse)
async def create_api_key(
    body: ApiKeyCreateRequest,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new API key. Returns the plain key ONCE — store it securely."""
    from app.core.api_key_auth import generate_api_key
    from app.core.config import settings as cfg

    if not cfg.FEATURE_PUBLIC_API:
        raise HTTPException(status_code=404, detail="Not found")

    plain_key, key_hash = generate_api_key()

    api_key = ApiKey(
        key_hash=key_hash,
        name=body.name,
        user_id=current_user.id,
        # Round-15 Sprint 15q cohort 7 — api_keys.tenant_id NOT NULL.
        tenant_id=current_user.tenant_id,
        scopes_json=body.scopes_json,
        rate_limit=body.rate_limit,
    )
    db.add(api_key)
    await db.flush()

    return {
        "message": "API anahtari olusturuldu. Bu anahtari guvenli bir yerde saklayin.",
        "id": api_key.id,
        "name": api_key.name,
        "api_key": plain_key,
    }


@router.delete("/api-keys/{key_id}", response_model=ApiKeyRevokeResponse)
async def revoke_api_key(
    key_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Revoke (deactivate) an API key."""
    from app.core.config import settings as cfg

    if not cfg.FEATURE_PUBLIC_API:
        raise HTTPException(status_code=404, detail="Not found")

    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == current_user.id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise NotFoundException("API anahtari bulunamadi")

    api_key.is_active = False
    await db.flush()

    return {"message": "API anahtari iptal edildi", "id": key_id}


# ── System Config ──


@router.get("/system-config", response_model=SystemConfigResponse)
async def get_system_config(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Expose non-secret config settings (manager only)."""
    from app.core.config import settings as cfg

    feature_flags = {
        "FEATURE_V2_BOARD": cfg.FEATURE_V2_BOARD,
        "FEATURE_AI_SUMMARIES": cfg.FEATURE_AI_SUMMARIES,
        "FEATURE_AI_PIPELINE_SUGGESTIONS": cfg.FEATURE_AI_PIPELINE_SUGGESTIONS,
        "FEATURE_LEAD_LIFECYCLE": cfg.FEATURE_LEAD_LIFECYCLE,
        "FEATURE_APPROVAL_ROUTING": cfg.FEATURE_APPROVAL_ROUTING,
        "FEATURE_DEAL_HEALTH": cfg.FEATURE_DEAL_HEALTH,
        "FEATURE_WEBHOOKS": cfg.FEATURE_WEBHOOKS,
        "FEATURE_TEAM_ACCESS": cfg.FEATURE_TEAM_ACCESS,
        "FEATURE_REPORT_BUILDER": cfg.FEATURE_REPORT_BUILDER,
        "FEATURE_REVENUE_COCKPIT": cfg.FEATURE_REVENUE_COCKPIT,
        "FEATURE_FIELD_PERMISSIONS": cfg.FEATURE_FIELD_PERMISSIONS,
        "FEATURE_PRODUCT_RULES": cfg.FEATURE_PRODUCT_RULES,
        "FEATURE_SESSION_MANAGEMENT": cfg.FEATURE_SESSION_MANAGEMENT,
        "FEATURE_GUIDED_SELLING": cfg.FEATURE_GUIDED_SELLING,
        "FEATURE_DASHBOARD_BUILDER": cfg.FEATURE_DASHBOARD_BUILDER,
        "FEATURE_PUBLIC_API": cfg.FEATURE_PUBLIC_API,
        "FEATURE_PWA": cfg.FEATURE_PWA,
        "FEATURE_CUSTOM_FIELDS": cfg.FEATURE_CUSTOM_FIELDS,
        "FEATURE_WORKFLOW_RULES": cfg.FEATURE_WORKFLOW_RULES,
    }

    return {
        "feature_flags": feature_flags,
        "rate_limits": {
            "login": cfg.RATE_LIMIT_LOGIN,
            "api": cfg.RATE_LIMIT_API,
        },
        "company": {
            "name": cfg.COMPANY_NAME,
            "address": cfg.COMPANY_ADDRESS,
            "phone": cfg.COMPANY_PHONE,
        },
        "quote_defaults": {
            "prefix": cfg.QUOTE_PREFIX,
            "default_tax_rate": cfg.DEFAULT_TAX_RATE,
            "default_currency": cfg.DEFAULT_CURRENCY,
            "validity_days": cfg.QUOTE_VALIDITY_DAYS,
        },
    }


class SystemConfigUpdate(BaseModel):
    value: str


@router.put("/system-config/{key}", response_model=SystemConfigUpdateResponse)
async def update_system_config(
    key: str,
    body: SystemConfigUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update a system setting via Setting table (manager only)."""
    # Whitelist of updatable keys to prevent arbitrary writes
    updatable_keys = {
        "company_name",
        "company_address",
        "company_phone",
        "quote_prefix",
        "default_tax_rate",
        "default_currency",
        "quote_validity_days",
    }

    if key not in updatable_keys:
        raise BadRequestException(
            f"Bu ayar guncellenemez: '{key}'. "
            f"Guncellenebilir ayarlar: {', '.join(sorted(updatable_keys))}"
        )

    result = await db.execute(select(Setting).where(Setting.key == key))
    setting = result.scalar_one_or_none()

    if setting:
        setting.value = body.value
    else:
        setting = Setting(key=key, value=body.value)
        db.add(setting)

    await db.flush()

    return {"message": f"Ayar guncellendi: {key}", "key": key, "value": body.value}


# ── Stage Configuration ──

_DEFAULT_STAGES = [
    {"stage_name": "prospecting", "label": "Kesfetme", "probability_pct": 10, "rotting_threshold_days": 7, "sort_order": 0},
    {"stage_name": "qualified", "label": "Nitelendirme", "probability_pct": 30, "rotting_threshold_days": 10, "sort_order": 1},
    {"stage_name": "proposal", "label": "Teklif", "probability_pct": 50, "rotting_threshold_days": 14, "sort_order": 2},
    {"stage_name": "negotiation", "label": "Muzakere", "probability_pct": 70, "rotting_threshold_days": 21, "sort_order": 3},
    {"stage_name": "closed_won", "label": "Kazanildi", "probability_pct": 100, "rotting_threshold_days": 0, "sort_order": 4},
    {"stage_name": "closed_lost", "label": "Kaybedildi", "probability_pct": 0, "rotting_threshold_days": 0, "sort_order": 5},
]


class StageConfigItem(BaseModel):
    stage_name: str
    label: str | None = None
    probability_pct: float
    rotting_threshold_days: int


class StageConfigBulkUpdate(BaseModel):
    stages: list[StageConfigItem]


@router.get("/stage-config", response_model=StageConfigListResponse)
async def get_stage_config(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return all stage configs. Creates defaults if table is empty."""
    result = await db.execute(
        select(StageConfig).order_by(StageConfig.sort_order)
    )
    configs = list(result.scalars().all())

    # Seed defaults if empty
    if not configs:
        for default in _DEFAULT_STAGES:
            cfg = StageConfig(**default)
            db.add(cfg)
        await db.flush()

        result = await db.execute(
            select(StageConfig).order_by(StageConfig.sort_order)
        )
        configs = list(result.scalars().all())

    return {
        "items": [
            {
                "id": c.id,
                "stage_name": c.stage_name,
                "label": c.label,
                "probability_pct": c.probability_pct,
                "rotting_threshold_days": c.rotting_threshold_days,
                "sort_order": c.sort_order,
                "is_active": c.is_active,
            }
            for c in configs
        ],
        "total": len(configs),
    }


# ── Notification Channels (Slack/Teams) ──

@router.get("/notification-channels", response_model=NotificationChannelsResponse)
async def get_notification_channels(
    current_user: User = Depends(get_current_user),
):
    """Return notification channel configuration status."""
    from app.core.config import settings as cfg

    return {
        "data": {
            "slack_configured": bool(cfg.SLACK_WEBHOOK_URL),
            "teams_configured": bool(cfg.TEAMS_WEBHOOK_URL),
        }
    }


@router.post(
    "/notification-channels/test",
    response_model=NotificationChannelsTestResponse,
)
async def test_notification_channel(
    body: dict,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
):
    """Test Slack/Teams webhook with a sample message."""
    from app.services.notification_channel_service import NotificationChannelService

    ncs = NotificationChannelService()
    test_msg = ncs.format_opportunity_card({
        "title": "Test Bildirimi",
        "stage": "proposal",
        "amount": "50000",
        "currency": "TRY",
        "owner": current_user.full_name,
        "customer": "Test Sirket",
    })

    results: dict[str, bool] = {}
    if body.get("slack_url"):
        results["slack"] = await ncs.send_slack(body["slack_url"], test_msg)
    if body.get("teams_url"):
        results["teams"] = await ncs.send_teams(body["teams_url"], test_msg)

    return {"data": results}


@router.put("/stage-config", response_model=StageConfigUpdateResponse)
async def update_stage_config(
    body: StageConfigBulkUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Bulk update all stage configs (sales_manager only)."""
    updated_count = 0

    for item in body.stages:
        result = await db.execute(
            select(StageConfig).where(StageConfig.stage_name == item.stage_name)
        )
        config = result.scalar_one_or_none()

        if config:
            config.probability_pct = item.probability_pct
            config.rotting_threshold_days = item.rotting_threshold_days
            if item.label is not None:
                config.label = item.label
            updated_count += 1
        else:
            config = StageConfig(
                stage_name=item.stage_name,
                label=item.label or item.stage_name,
                probability_pct=item.probability_pct,
                rotting_threshold_days=item.rotting_threshold_days,
            )
            db.add(config)
            updated_count += 1

    await db.flush()

    # Invalidate cached probabilities in forecast service
    from app.services.forecast_service import _stage_probability_cache
    _stage_probability_cache.clear()

    return {"message": f"{updated_count} asama guncellendi", "updated": updated_count}
