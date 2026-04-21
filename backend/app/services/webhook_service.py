"""Webhook delivery service — subscribes to event bus, delivers to external URLs."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import urllib.parse
from datetime import datetime, timezone
from secrets import token_hex
from typing import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.webhook import WebhookDelivery, WebhookSubscription

logger = logging.getLogger(__name__)

DELIVERY_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BODY_LENGTH = 1000
MAX_FAILURE_COUNT = 10


_BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
)


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # ipaddress covers RFC1918 + loopback + link-local + unspecified etc.
    if ip.is_loopback:
        return True
    if ip.is_private:
        return True
    if ip.is_link_local:
        return True
    if ip.is_multicast:
        return True
    if ip.is_reserved:
        return True
    if ip.is_unspecified:
        return True
    return False


def _resolve_host(hostname: str) -> set[ipaddress._BaseAddress]:
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Webhook URL hostname cozumlenemedi: '{hostname}'.") from exc

    ips: set[ipaddress._BaseAddress] = set()
    for addr_info in addr_infos:
        ips.add(ipaddress.ip_address(addr_info[4][0]))
    return ips


def validate_webhook_url(url: str) -> None:
    """Validate webhook URL against SSRF attacks.

    Checks protocol and resolves hostname to ensure it does not
    point to internal/private network addresses.

    Raises ValueError if the URL is blocked.
    """
    parsed = urllib.parse.urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Gecersiz webhook URL protokolu: '{parsed.scheme}'. "
            "Yalnizca http ve https desteklenir."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Webhook URL'sinde gecerli bir hostname bulunamadi.")

    # Reject userinfo to avoid confusing downstream proxies/logging.
    if parsed.username or parsed.password:
        raise ValueError("Webhook URL userinfo (kullanici:parola) iceremez.")

    hn = hostname.strip().lower().rstrip(".")
    if hn == "localhost" or hn.endswith(_BLOCKED_HOST_SUFFIXES):
        raise ValueError("Webhook URL localhost/local/internal alan adlarina gonderilemez.")

    # Explicit port policy: allow default ports only (80/443) unless unset.
    if parsed.port is not None and parsed.port not in (80, 443):
        raise ValueError("Webhook URL yalnizca 80/443 portlarina gonderebilir.")

    ips = _resolve_host(hn)
    for ip in ips:
        if _is_blocked_ip(ip):
            raise ValueError(
                "Webhook URL'si engellenmis bir IP'ye isaret ediyor: "
                f"{ip}. Dahili/ozel ag adreslerine webhook gonderimi yapilmaz."
            )


def _build_webhook_headers(secret: str | None, body: str) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if not secret:
        return headers

    # Legacy signature (body only)
    sig_legacy = hmac.new(
        secret.encode("utf-8"),
        body.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    headers["X-Webhook-Signature"] = f"sha256={sig_legacy}"

    # V2 signature includes timestamp+nonce to enable replay protection on the receiver side.
    ts = str(int(datetime.now(timezone.utc).timestamp()))
    nonce = token_hex(16)
    signing_input = f"{ts}.{nonce}.{body}".encode("utf-8")
    sig_v2 = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).hexdigest()
    headers["X-Webhook-Timestamp"] = ts
    headers["X-Webhook-Nonce"] = nonce
    headers["X-Webhook-Signature-V2"] = f"t={ts},nonce={nonce},sha256={sig_v2}"
    return headers


class WebhookService:
    """Delivers events to registered webhook subscriptions."""

    def __init__(self, db_session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = db_session_factory

    async def handle_event(self, event_type: str, payload: dict) -> None:
        """Event bus handler — find matching subscriptions, deliver.

        This method matches the EventBus handler signature:
        (event_type: str, payload: dict) -> None
        """
        async with self._session_factory() as db:
            try:
                result = await db.execute(
                    select(WebhookSubscription).where(
                        WebhookSubscription.is_active.is_(True)
                    )
                )
                subscriptions = result.scalars().all()

                for sub in subscriptions:
                    if not self._matches_event(sub, event_type):
                        continue
                    await self._deliver(db, sub, event_type, payload)

                await db.commit()
            except Exception as exc:
                logger.error("Webhook event handling failed: %s", exc)
                await db.rollback()

    async def deliver_test(self, db: AsyncSession, subscription_id: int) -> dict:
        """Send a test event to a specific subscription."""
        result = await db.execute(
            select(WebhookSubscription).where(
                WebhookSubscription.id == subscription_id
            )
        )
        subscription = result.scalar_one_or_none()
        if subscription is None:
            return {"success": False, "error": "Abonelik bulunamadi."}

        test_payload = {
            "event": "webhook.test",
            "subscription_id": subscription.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": "Bu bir test etkinligidir.",
        }

        validate_webhook_url(subscription.url)

        delivery = await self._deliver(db, subscription, "webhook.test", test_payload)
        await db.commit()

        is_success = delivery.status_code is not None and 200 <= delivery.status_code < 300
        return {
            "success": is_success,
            "status_code": delivery.status_code,
            "response_body": delivery.response_body,
        }

    async def _deliver(
        self,
        db: AsyncSession,
        subscription: WebhookSubscription,
        event_type: str,
        payload: dict,
    ) -> WebhookDelivery:
        """POST to URL with JSON body + X-Webhook-Signature header (HMAC-SHA256)."""
        validate_webhook_url(subscription.url)

        body = json.dumps(payload, default=str, ensure_ascii=False)
        headers = _build_webhook_headers(subscription.secret, body)

        status_code = None
        response_body = None

        try:
            # Re-validate right before the request as a best-effort DNS rebinding guard.
            # (We still rely on the resolver used by the HTTP client; follow_redirects is disabled.)
            validate_webhook_url(subscription.url)

            async with httpx.AsyncClient(
                timeout=DELIVERY_TIMEOUT_SECONDS,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    subscription.url,
                    content=body,
                    headers=headers,
                )
                status_code = response.status_code
                response_body = response.text[:MAX_RESPONSE_BODY_LENGTH]

            is_success = 200 <= status_code < 300
            if is_success:
                subscription.failure_count = 0
            else:
                subscription.failure_count += 1
                logger.warning(
                    "Webhook delivery failed for %s: HTTP %s",
                    subscription.name,
                    status_code,
                )

        except httpx.TimeoutException:
            subscription.failure_count += 1
            response_body = "Zaman asimi hatasi"
            logger.warning("Webhook delivery timed out for %s", subscription.name)

        except Exception as exc:
            subscription.failure_count += 1
            response_body = str(exc)[:MAX_RESPONSE_BODY_LENGTH]
            logger.warning("Webhook delivery error for %s: %s", subscription.name, exc)

        # Auto-disable after too many failures
        if subscription.failure_count >= MAX_FAILURE_COUNT:
            subscription.is_active = False
            logger.warning(
                "Webhook %s devre disi birakildi: %d ardisik basarisiz teslimat.",
                subscription.name,
                subscription.failure_count,
            )

        subscription.last_triggered_at = datetime.now(timezone.utc)

        delivery = WebhookDelivery(
            subscription_id=subscription.id,
            event_type=event_type,
            payload_json=body,
            status_code=status_code,
            response_body=response_body,
            delivered_at=datetime.now(timezone.utc),
        )
        db.add(delivery)

        return delivery

    @staticmethod
    def _matches_event(subscription: WebhookSubscription, event_type: str) -> bool:
        """Check if subscription listens for this event type."""
        try:
            event_types = json.loads(subscription.event_types)
        except (json.JSONDecodeError, TypeError):
            return False

        if "*" in event_types:
            return True

        return event_type in event_types

    def create_event_handler(self) -> Callable:
        """Return a bound handler suitable for EventBus.subscribe()."""
        return self.handle_event
