"""Customer enrichment service — Claude AI-powered company data enrichment."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import CircuitOpenError
from app.core.claude_client import claude_messages_create
from app.core.config import settings
from app.models.customer import Customer

logger = logging.getLogger(__name__)


class EnrichmentService:
    """Enrich customer records with company data via Claude AI."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def enrich_customer(self, customer_id: int) -> dict:
        """Use Claude AI to enrich customer data based on company name and email domain."""
        customer = await self.db.get(Customer, customer_id)
        if not customer:
            raise ValueError("Musteri bulunamadi")

        domain = customer.email.split("@")[1] if "@" in customer.email else ""
        prompt = (
            f"Analyze this company and return structured JSON:\n"
            f"Company: {customer.company or customer.name}\n"
            f"Email domain: {domain}\n"
            f"Country: Turkey\n\n"
            f"Return ONLY valid JSON:\n"
            f'{{"industry": "...", "employee_count": N, '
            f'"annual_revenue": "$XM-YM", '
            f'"website": "https://...", '
            f'"linkedin_url": "https://linkedin.com/company/...", '
            f'"description": "1-2 sentence summary"}}\n\n'
            f"If unknown, use null for that field."
        )

        data = await self._fetch_enrichment_data(prompt, domain)
        self._apply_enrichment(customer, data)
        await self.db.commit()

        return data

    async def _fetch_enrichment_data(self, prompt: str, domain: str) -> dict:
        """Fetch enrichment data from Claude AI or fall back to basic enrichment."""
        if settings.ANTHROPIC_API_KEY:
            try:
                return await self._call_claude(prompt)
            except CircuitOpenError as exc:
                logger.warning(
                    "Claude breaker open; using basic enrichment fallback: %s", exc
                )
                return self._basic_fallback(domain)

        return self._basic_fallback(domain)

    async def _call_claude(self, prompt: str) -> dict:
        """Call Claude API and parse the JSON response."""
        response = await claude_messages_create(
            model=settings.AI_MODEL_NAME,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        if "```" in text:
            text = text.split("```")[1].strip()
            if text.startswith("json"):
                text = text[4:].strip()

        return json.loads(text)

    @staticmethod
    def _basic_fallback(domain: str) -> dict:
        """Basic enrichment from email domain when no API key is configured."""
        return {
            "industry": None,
            "employee_count": None,
            "annual_revenue": None,
            "website": f"https://{domain}" if domain else None,
            "linkedin_url": None,
        }

    @staticmethod
    def _apply_enrichment(customer: Customer, data: dict) -> None:
        """Apply enrichment data to the customer record."""
        customer.industry = data.get("industry")
        customer.employee_count = data.get("employee_count")
        customer.annual_revenue = data.get("annual_revenue")
        customer.website = data.get("website")
        customer.linkedin_url = data.get("linkedin_url")
        customer.enriched_at = datetime.now(timezone.utc)
