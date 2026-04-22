"""Marketplace / plugin runtime helpers.

Two public entry points:

    :func:`install_plugin`   - bind a published plugin to a tenant,
                               generate an API token, record granted scopes.
    :func:`dispatch_event`   - fan an event out to every active subscription
                               belonging to an installed plugin.

Webhook delivery is best-effort HTTP POST. We hash the shared secret and
send an HMAC-SHA256 signature in the ``X-Signature`` header so plugin
authors can verify payloads.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import encrypt_str
from app.models.marketplace import (
    Plugin,
    PluginEventSubscription,
    PluginInstallation,
)

logger = logging.getLogger(__name__)

DELIVERY_TIMEOUT = 10.0
SIGNATURE_HEADER = "X-Marketplace-Signature"


class MarketplaceError(Exception):
    pass


class ScopeDenied(MarketplaceError):
    pass


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _mint_token() -> tuple[str, str]:
    plain = "mkt_" + secrets.token_urlsafe(32)
    return plain, encrypt_str(plain)


# ── Install / uninstall ─────────────────────────────────────────────────────


async def install_plugin(
    db: AsyncSession,
    *,
    plugin_slug: str,
    tenant_id: int = 1,
    granted_scopes: list[str],
    installed_by: int | None,
    config: dict | None = None,
) -> tuple[PluginInstallation, str]:
    plugin = (
        await db.execute(select(Plugin).where(Plugin.slug == plugin_slug))
    ).scalar_one_or_none()
    if not plugin or not plugin.is_active:
        raise MarketplaceError(f"Unknown or inactive plugin: {plugin_slug}")

    try:
        allowed_scopes = set(json.loads(plugin.scopes_json or "[]"))
    except json.JSONDecodeError:
        allowed_scopes = set()
    requested = set(granted_scopes or [])
    if not requested.issubset(allowed_scopes):
        raise ScopeDenied(
            f"Scopes {sorted(requested - allowed_scopes)} not offered by plugin"
        )

    existing = (
        await db.execute(
            select(PluginInstallation).where(
                PluginInstallation.plugin_id == plugin.id,
                PluginInstallation.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if existing and existing.status == "active":
        raise MarketplaceError("Plugin already installed for this tenant")

    plain_token, encrypted_token = _mint_token()
    installation = existing or PluginInstallation(
        plugin_id=plugin.id,
        tenant_id=tenant_id,
    )
    installation.status = "active"
    installation.granted_scopes_json = json.dumps(sorted(requested), ensure_ascii=False)
    installation.api_token_encrypted = encrypted_token
    installation.config_json = json.dumps(config or {}, ensure_ascii=False)
    installation.installed_by = installed_by
    installation.installed_at = datetime.now(timezone.utc)
    installation.uninstalled_at = None

    if not existing:
        db.add(installation)
    await db.flush()
    return installation, plain_token


async def uninstall_plugin(
    db: AsyncSession, *, installation_id: int
) -> None:
    installation = await db.get(PluginInstallation, installation_id)
    if not installation:
        raise MarketplaceError("Installation not found")
    installation.status = "uninstalled"
    installation.uninstalled_at = datetime.now(timezone.utc)
    # Cascade deletes on subscriptions via cascade="all, delete-orphan".
    installation.subscriptions.clear()


async def add_subscription(
    db: AsyncSession,
    *,
    installation: PluginInstallation,
    event_type: str,
    target_url: str,
    secret: str | None = None,
) -> PluginEventSubscription:
    """Register a webhook subscription. ``secret`` is hashed, not stored raw."""
    allowed_events = _parse_events(installation.plugin.events_json)
    if allowed_events and event_type not in allowed_events and "*" not in allowed_events:
        raise ScopeDenied(f"Event {event_type} not declared by plugin")

    row = PluginEventSubscription(
        installation_id=installation.id,
        event_type=event_type,
        target_url=target_url,
        secret_hash=_hash_secret(secret) if secret else None,
    )
    db.add(row)
    await db.flush()
    return row


def _parse_events(raw: str | None) -> set[str]:
    if not raw:
        return set()
    try:
        return set(json.loads(raw))
    except json.JSONDecodeError:
        return set()


# ── Event dispatch ──────────────────────────────────────────────────────────


async def dispatch_event(
    session_factory,
    *,
    event_type: str,
    payload: dict,
) -> int:
    """Fan an event out to every active subscription.

    Returns the number of delivery attempts made. Failures are logged but
    never raised so the event bus keeps running for other subscribers.
    """
    async with session_factory() as db:
        subs = (
            await db.execute(
                select(PluginEventSubscription)
                .where(
                    PluginEventSubscription.event_type.in_({event_type, "*"}),
                    PluginEventSubscription.is_active.is_(True),
                )
            )
        ).scalars().all()

        if not subs:
            return 0

        installations = {}
        for sub in subs:
            inst = await db.get(PluginInstallation, sub.installation_id)
            if inst and inst.status == "active":
                installations[sub.id] = inst

    tasks = []
    for sub in subs:
        inst = installations.get(sub.id)
        if not inst:
            continue
        tasks.append(_deliver(sub, payload, event_type))

    if not tasks:
        return 0
    await asyncio.gather(*tasks, return_exceptions=True)
    return len(tasks)


async def _deliver(sub: PluginEventSubscription, payload: dict, event_type: str) -> None:
    body = json.dumps(
        {"event": event_type, "payload": payload, "delivered_at": datetime.now(timezone.utc).isoformat()},
        default=str,
        ensure_ascii=False,
    )
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if sub.secret_hash:
        # We don't have the plaintext secret after storage; signature covers
        # payload hash so the plugin author can still verify integrity.
        signature = hmac.new(
            sub.secret_hash.encode("utf-8"), body.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        headers[SIGNATURE_HEADER] = signature

    try:
        async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT) as client:
            resp = await client.post(sub.target_url, content=body, headers=headers)
        if resp.status_code >= 400:
            logger.warning(
                "marketplace.webhook.fail sub=%s url=%s status=%s",
                sub.id, sub.target_url, resp.status_code,
            )
    except Exception as exc:  # pragma: no cover - network exceptional
        logger.warning("marketplace.webhook.error sub=%s err=%s", sub.id, exc)
