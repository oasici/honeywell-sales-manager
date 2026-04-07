import os
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException
from app.models.enums import UserRole
from app.models.setting import Setting
from app.models.user import User

router = APIRouter(prefix="/settings", tags=["Settings"])


# ── Password encryption helpers ──

def _get_fernet():
    from app.core.config import settings as cfg

    key = os.environ.get("ENCRYPTION_KEY", "")
    if not key:
        if cfg.is_production:
            raise RuntimeError(
                "ENCRYPTION_KEY must be set in production. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
        # Development/test: auto-generate and persist for the process lifetime
        key = Fernet.generate_key().decode()
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

@router.get("/")
async def get_settings(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Get all settings as a key-value map (sales_manager only)."""
    result = await db.execute(select(Setting).order_by(Setting.key))
    settings = result.scalars().all()

    settings_dict = {s.key: s.value for s in settings}

    # Never expose password - show masked version
    if "email_password" in settings_dict:
        settings_dict["email_password"] = "********"

    return {"settings": settings_dict}


@router.put("/")
async def update_settings(
    data: SettingsUpdateRequest,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update settings from a validated request body."""
    updated_keys = []

    for key, value in data.model_dump(exclude_none=True).items():

        result = await db.execute(select(Setting).where(Setting.key == key))
        setting = result.scalar_one_or_none()

        if setting:
            setting.value = str(value) if value is not None else None
        else:
            setting = Setting(
                key=key,
                value=str(value) if value is not None else None,
            )
            db.add(setting)

        updated_keys.append(key)

    await db.flush()

    all_result = await db.execute(select(Setting).order_by(Setting.key))
    all_settings = all_result.scalars().all()
    settings_dict = {s.key: s.value for s in all_settings}
    if "email_password" in settings_dict:
        settings_dict["email_password"] = "********"

    return {
        "message": f"Updated {len(updated_keys)} setting(s)",
        "updated_keys": updated_keys,
        "settings": settings_dict,
    }


# ── Email Credentials ──

@router.post("/email-credentials")
async def save_email_credentials(
    body: EmailCredentials,
    current_user: User = Depends(get_current_user),
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


@router.get("/email-credentials")
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


@router.post("/email-credentials/test")
async def test_email_connection(
    body: EmailTestRequest | None = None,
    current_user: User = Depends(get_current_user),
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

    # Always auto-detect if host doesn't match email domain
    detected_h, detected_p, _, _ = _detect_provider(email_addr)
    default_hosts = {"", "outlook.office365.com"}
    if not imap_host or imap_host in default_hosts:
        imap_host = detected_h
        imap_port = detected_p

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
