"""Tests for AI email triage service."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_request import EmailRequest
from app.services.ai_email_triage import _rule_based_triage, triage_email


@pytest_asyncio.fixture
async def sample_email(db: AsyncSession) -> EmailRequest:
    email = EmailRequest(
        message_id="test-triage-001@example.com",
        from_address="customer@example.com",
        subject="Normal talep",
        body_text="Urun katalogunuzu gonderir misiniz?",
        status="new",
    )
    db.add(email)
    await db.flush()
    await db.refresh(email)
    return email


@pytest.mark.asyncio
async def test_rule_based_triage_low_priority(sample_email: EmailRequest):
    """Normal emails without urgency keywords should be classified as low priority."""
    combined = f"{sample_email.subject} {sample_email.body_text}".lower()
    result = _rule_based_triage(sample_email, combined)

    assert result["priority"] == "low"
    assert "reason" in result


@pytest.mark.asyncio
async def test_urgent_keywords_yield_urgent_priority(db: AsyncSession):
    """Emails with urgent keywords should be classified as urgent."""
    email = EmailRequest(
        message_id="test-triage-002@example.com",
        from_address="customer@example.com",
        subject="ACIL: Hat durdu, yedek parca lazim",
        body_text="Uretim hatti durdu, acil olarak pompa yedek parcasi gerekiyor.",
        status="new",
    )
    db.add(email)
    await db.flush()
    await db.refresh(email)

    combined = f"{email.subject} {email.body_text}".lower()
    result = _rule_based_triage(email, combined)

    assert result["priority"] == "urgent"
    assert "acil" in result["reason"].lower()


@pytest.mark.asyncio
async def test_negative_sentiment_yields_high_priority(db: AsyncSession):
    """Emails with negative sentiment keywords should be classified as high priority."""
    email = EmailRequest(
        message_id="test-triage-003@example.com",
        from_address="customer@example.com",
        subject="Sikayet: Gecikme",
        body_text="Siparis gecikti ve sorun yasiyoruz. Memnuniyetsizligimizi bildiririz.",
        status="new",
        sentiment="negative",
    )
    db.add(email)
    await db.flush()
    await db.refresh(email)

    combined = f"{email.subject} {email.body_text}".lower()
    result = _rule_based_triage(email, combined)

    assert result["priority"] == "high"
