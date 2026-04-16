"""Slack and Teams notification channel service via incoming webhooks."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_SECONDS = 10


class NotificationChannelService:
    """Send formatted messages to Slack and Microsoft Teams via webhooks."""

    @staticmethod
    async def send_slack(webhook_url: str, message: dict) -> bool:
        """Send Slack Block Kit message via incoming webhook."""
        import httpx

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    webhook_url,
                    json=message,
                    timeout=WEBHOOK_TIMEOUT_SECONDS,
                )
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("Slack bildirimi gonderilemedi: %s", exc)
            return False

    @staticmethod
    async def send_teams(webhook_url: str, message: dict) -> bool:
        """Send Teams Adaptive Card via incoming webhook."""
        import httpx

        card = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": message.get("summary", "Bildirim"),
            "themeColor": "D6001C",
            "sections": [
                {
                    "activityTitle": message.get("title", "Honeywell Sales Manager"),
                    "facts": message.get("facts", []),
                    "markdown": True,
                }
            ],
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    webhook_url,
                    json=card,
                    timeout=WEBHOOK_TIMEOUT_SECONDS,
                )
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("Teams bildirimi gonderilemedi: %s", exc)
            return False

    @staticmethod
    def format_opportunity_card(opp_data: dict) -> dict:
        """Format opportunity data as Slack Block Kit message."""
        title = opp_data.get("title", "Firsat")
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": title},
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Asama:* {opp_data.get('stage', '-')}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Tutar:* {opp_data.get('amount', '-')} {opp_data.get('currency', 'TRY')}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Sahip:* {opp_data.get('owner', '-')}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Musteri:* {opp_data.get('customer', '-')}",
                        },
                    ],
                },
            ],
            # Teams-compatible fields
            "summary": title,
            "title": title,
            "facts": [
                {"name": "Asama", "value": opp_data.get("stage", "-")},
                {
                    "name": "Tutar",
                    "value": f"{opp_data.get('amount', '-')} {opp_data.get('currency', 'TRY')}",
                },
                {"name": "Sahip", "value": opp_data.get("owner", "-")},
                {"name": "Musteri", "value": opp_data.get("customer", "-")},
            ],
        }

    @staticmethod
    def format_deal_won_card(opp_data: dict) -> dict:
        """Celebration card for won deals."""
        title = f"Kazanildi: {opp_data.get('title', 'Firsat')}"
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": title},
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Tutar:* {opp_data.get('amount', '-')} {opp_data.get('currency', 'TRY')}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Sahip:* {opp_data.get('owner', '-')}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Musteri:* {opp_data.get('customer', '-')}",
                        },
                    ],
                },
            ],
            "summary": title,
            "title": title,
            "facts": [
                {
                    "name": "Tutar",
                    "value": f"{opp_data.get('amount', '-')} {opp_data.get('currency', 'TRY')}",
                },
                {"name": "Sahip", "value": opp_data.get("owner", "-")},
                {"name": "Musteri", "value": opp_data.get("customer", "-")},
            ],
        }

    @staticmethod
    def format_quote_card(quote_data: dict) -> dict:
        """Format quote data as Slack message."""
        title = f"Teklif: {quote_data.get('quote_number', '-')}"
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": title},
                },
                {
                    "type": "section",
                    "fields": [
                        {
                            "type": "mrkdwn",
                            "text": f"*Durum:* {quote_data.get('status', '-')}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Toplam:* {quote_data.get('grand_total', '-')} {quote_data.get('currency', 'TRY')}",
                        },
                        {
                            "type": "mrkdwn",
                            "text": f"*Musteri:* {quote_data.get('customer', '-')}",
                        },
                    ],
                },
            ],
            "summary": title,
            "title": title,
            "facts": [
                {"name": "Durum", "value": quote_data.get("status", "-")},
                {
                    "name": "Toplam",
                    "value": f"{quote_data.get('grand_total', '-')} {quote_data.get('currency', 'TRY')}",
                },
                {"name": "Musteri", "value": quote_data.get("customer", "-")},
            ],
        }
