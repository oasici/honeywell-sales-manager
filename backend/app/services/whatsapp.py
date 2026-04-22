"""Meta Cloud API client + inbound webhook helpers for WhatsApp Business.

Endpoint docs: https://developers.facebook.com/docs/whatsapp/cloud-api

Credentials come from settings:

    WHATSAPP_PHONE_NUMBER_ID
    WHATSAPP_ACCESS_TOKEN
    WHATSAPP_VERIFY_TOKEN      (for the GET subscribe handshake)
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.facebook.com/v19.0"
_TIMEOUT = 20.0


class WhatsAppError(Exception):
    """Raised when Meta's API rejects a request."""


_E164 = re.compile(r"^\+?[1-9]\d{7,14}$")


def normalize_phone(value: str) -> str:
    """Return E.164 form for a possibly-Turkish input (strip spaces/dashes)."""
    cleaned = re.sub(r"[^\d+]", "", value or "")
    if not cleaned:
        raise WhatsAppError("empty phone number")
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
    if not cleaned.startswith("+"):
        # Treat bare national numbers as Turkish if they look like it.
        if cleaned.startswith("0") and len(cleaned) == 11:
            cleaned = "+90" + cleaned[1:]
        elif len(cleaned) == 10:
            cleaned = "+90" + cleaned
        else:
            cleaned = "+" + cleaned
    if not _E164.match(cleaned):
        raise WhatsAppError(f"invalid phone number: {value!r}")
    return cleaned


async def send_text(to: str, body: str) -> dict[str, Any]:
    """Send a free-form text message. Requires an active 24h session."""
    if not settings.WHATSAPP_PHONE_NUMBER_ID or not settings.WHATSAPP_ACCESS_TOKEN:
        raise WhatsAppError("WhatsApp credentials not configured")

    url = f"{_GRAPH_BASE}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": normalize_phone(to),
        "type": "text",
        "text": {"body": body[:4096]},
    }
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
        )
    if resp.status_code >= 400:
        raise WhatsAppError(f"WhatsApp send failed {resp.status_code}: {resp.text[:200]}")
    return resp.json()


async def send_template(
    to: str,
    template_name: str,
    *,
    language: str = "tr",
    components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Send a pre-approved template message (required outside the 24h window)."""
    if not settings.WHATSAPP_PHONE_NUMBER_ID or not settings.WHATSAPP_ACCESS_TOKEN:
        raise WhatsAppError("WhatsApp credentials not configured")

    url = f"{_GRAPH_BASE}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": normalize_phone(to),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
        },
    }
    if components:
        payload["template"]["components"] = components

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
        )
    if resp.status_code >= 400:
        raise WhatsAppError(
            f"WhatsApp template send failed {resp.status_code}: {resp.text[:200]}"
        )
    return resp.json()


def parse_inbound(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert a webhook ``entry`` payload into flat inbound message dicts.

    Meta's webhook packs messages inside nested ``entry[*].changes[*].value``.
    This helper normalizes that shape; ignore anything not of type
    ``messages`` (status receipts go through a separate path).
    """
    normalized: list[dict[str, Any]] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            value = change.get("value", {})
            for message in value.get("messages", []):
                normalized.append(
                    {
                        "wa_message_id": message.get("id"),
                        "phone_number": "+" + str(message.get("from", "")).lstrip("+"),
                        "type": message.get("type"),
                        "text": (message.get("text") or {}).get("body") or "",
                        "timestamp": message.get("timestamp"),
                    }
                )
    return normalized


def verify_webhook_challenge(mode: str, token: str, challenge: str) -> str | None:
    """Return ``challenge`` when the handshake is valid, otherwise None."""
    if mode != "subscribe":
        return None
    if not settings.WHATSAPP_VERIFY_TOKEN:
        return None
    if token != settings.WHATSAPP_VERIFY_TOKEN:
        return None
    return challenge
