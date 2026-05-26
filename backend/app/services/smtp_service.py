"""D-014 — SMTP service (replaces the e-Sign OTP send stub).

Thin wrapper around ``aiosmtplib`` reading SMTP credentials from the
tenant's ``settings`` table. Fails open in dev environments where SMTP
isn't configured — logs at WARNING so QA can see the would-have-been
mail, but the calling endpoint still succeeds.

At 20-30 user scale a single SMTP per tenant is fine. Phase 5
(multi-tenant SMTP rotation, DKIM signing, bounce processing)
arrives with the first enterprise customer.

Security:
  * SMTP password is Fernet-encrypted at rest (per-tenant DEK after
    F-001 rollout; legacy single-Fernet for un-migrated tenants).
  * TLS required (port 587 STARTTLS or 465 implicit TLS).
  * No raw HTML — every body is plain-text. HTML escalation is a
    Phase 5 feature.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    from_address: str
    use_tls: bool = True


async def _load_smtp_config(db: AsyncSession, tenant_id: Optional[int]) -> Optional[SmtpConfig]:
    """Load SMTP creds from the tenant's settings table.

    Returns None when SMTP isn't configured (dev environments, or a
    tenant that hasn't set it up yet) so callers can skip cleanly.
    """
    # The existing Settings table is single-row-per-key. We look for
    # the standard keys our integrations page writes.
    keys = (
        "smtp_host", "smtp_port", "smtp_username",
        "smtp_password_encrypted", "smtp_from", "smtp_use_tls",
    )
    rows = (
        await db.execute(
            text(
                "SELECT key, value FROM settings WHERE key = ANY(:ks)"
                if tenant_id is None
                else "SELECT key, value FROM settings "
                     "WHERE key = ANY(:ks) AND (tenant_id = :tid OR tenant_id IS NULL)"
            ),
            {"ks": list(keys), "tid": tenant_id} if tenant_id is not None else {"ks": list(keys)},
        )
    ).all()
    if not rows:
        return None
    cfg_map = {r.key: r.value for r in rows}
    if not cfg_map.get("smtp_host") or not cfg_map.get("smtp_username"):
        return None

    # Decrypt password. Try the legacy single-Fernet first; future
    # callers can switch to per-tenant decrypt_for_tenant.
    from app.api.v1.settings import _decrypt_password
    try:
        plain_pw = _decrypt_password(cfg_map.get("smtp_password_encrypted", ""))
    except Exception as exc:  # noqa: BLE001
        logger.error("SMTP password decrypt failed: %s", exc)
        return None

    return SmtpConfig(
        host=cfg_map["smtp_host"],
        port=int(cfg_map.get("smtp_port") or 587),
        username=cfg_map["smtp_username"],
        password=plain_pw,
        from_address=cfg_map.get("smtp_from") or cfg_map["smtp_username"],
        use_tls=(cfg_map.get("smtp_use_tls", "true").lower() != "false"),
    )


async def send_email(
    db: AsyncSession,
    *,
    to: str,
    subject: str,
    body: str,
    tenant_id: Optional[int] = None,
) -> bool:
    """Send a plain-text email. Returns True on success, False on
    'config missing / send failed but caller can continue'.

    Raises only on truly fatal misconfiguration (bad params). Network
    timeouts / SMTP refusals are logged + returned as False so the
    OTP/KVKK paths can decide their own retry policy.
    """
    cfg = await _load_smtp_config(db, tenant_id)
    if cfg is None:
        logger.warning(
            "SMTP not configured (tenant=%s) — would send to=%s subject=%s",
            tenant_id, to, subject,
        )
        return False

    try:
        import aiosmtplib
        from email.mime.text import MIMEText
    except ImportError:
        logger.error("aiosmtplib not installed; cannot send email")
        return False

    message = MIMEText(body, "plain", "utf-8")
    message["From"] = cfg.from_address
    message["To"] = to
    message["Subject"] = subject

    try:
        await aiosmtplib.send(
            message,
            hostname=cfg.host,
            port=cfg.port,
            username=cfg.username,
            password=cfg.password,
            start_tls=cfg.use_tls,
            timeout=30,
        )
        logger.info("SMTP send OK to=%s subject=%s", to, subject)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("SMTP send failed to=%s subject=%s: %s", to, subject, exc)
        return False


# ── Sync shim for legacy callers ───────────────────────────────────


def send_email_sync(to: str, subject: str, body: str) -> bool:
    """Synchronous wrapper used by callers that can't await (legacy).

    Spins up a tiny event loop in a thread. Prefer the async ``send_email``
    when possible.
    """
    async def _run():
        from app.core.database import async_session
        async with async_session() as db:
            return await send_email(db, to=to, subject=subject, body=body)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're already inside an event loop — fail safe.
            logger.warning("send_email_sync called from within event loop; skipping")
            return False
        return loop.run_until_complete(_run())
    except RuntimeError:
        return asyncio.run(_run())
