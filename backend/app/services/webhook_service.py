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
from typing import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.webhook import WebhookDelivery, WebhookSubscription

logger = logging.getLogger(__name__)

DELIVERY_TIMEOUT_SECONDS = 10
MAX_RESPONSE_BODY_LENGTH = 1000
MAX_FAILURE_COUNT = 10


BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
]


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

    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise ValueError(
            f"Webhook URL hostname cozumlenemedi: '{hostname}'."
        )

    for addr_info in addr_infos:
        ip = ipaddress.ip_address(addr_info[4][0])
        for network in BLOCKED_NETWORKS:
            if ip in network:
                raise ValueError(
                    f"Webhook URL'si engellenmis bir ag adresine isaret ediyor: "
                    f"{ip} ({network}). Dahili/ozel ag adreslerine "
                    "webhook gonderimi yapilmaz."
                )


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
        headers = {"Content-Type": "application/json"}

        if subscription.secret:
            signature = hmac.new(
                subscription.secret.encode("utf-8"),
                body.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            headers["X-Webhook-Signature"] = f"sha256={signature}"

        status_code = None
        response_body = None

        try:
            async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as client:
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
