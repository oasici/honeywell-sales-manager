"""Smart email triage — classify email priority using Claude or rule-based fallback."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.email_request import EmailRequest

logger = logging.getLogger(__name__)

URGENT_KEYWORDS = [
    "acil", "urgent", "hemen", "derhal", "asap", "kritik", "critical",
    "bugün", "today", "son gün", "deadline", "tehlike", "arıza", "duruş",
]

HIGH_PRIORITY_KEYWORDS = [
    "önemli", "important", "sipariş", "order", "teklif", "fiyat",
    "sözleşme", "contract", "ihale", "tender", "karar", "decision",
]

NEGATIVE_SENTIMENT_KEYWORDS = [
    "şikayet", "complaint", "sorun", "problem", "memnuniyetsiz",
    "dissatisfied", "gecikme", "delay", "hata", "error", "iptal", "cancel",
]


async def triage_email(db: AsyncSession, email_id: int) -> dict:
    """Classify email priority using Claude (or rule-based fallback).

    Considers: sender, keyword urgency, email category, sentiment.
    Returns {priority, reason}.
    """
    email = (
        await db.execute(select(EmailRequest).where(EmailRequest.id == email_id))
    ).scalar_one_or_none()

    if not email:
        return {"priority": None, "reason": "Email bulunamadi"}

    combined_text = f"{email.subject or ''} {email.body_text or ''}".lower()

    # Strategy 1: Claude AI triage
    if settings.ANTHROPIC_API_KEY:
        ai_result = await _claude_triage(email, combined_text)
        if ai_result:
            email.priority = ai_result["priority"]
            email.triage_reason = ai_result["reason"]
            await db.flush()
            return ai_result

    # Strategy 2: Rule-based fallback
    result = _rule_based_triage(email, combined_text)
    email.priority = result["priority"]
    email.triage_reason = result["reason"]
    await db.flush()
    return result


async def _claude_triage(email: EmailRequest, combined_text: str) -> dict | None:
    """Use Claude to classify email priority."""
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        prompt = (
            "Asagidaki satis emailinin oncelik seviyesini belirle.\n"
            f"Gonderen: {email.from_address}\n"
            f"Konu: {email.subject or 'Yok'}\n"
            f"Kategori: {email.category or 'Bilinmiyor'}\n"
            f"Duygu: {email.sentiment or 'Bilinmiyor'}\n\n"
            f"Icerik (ilk 2000 karakter):\n{combined_text[:2000]}\n\n"
            'JSON formatinda cevap ver: {"priority": "urgent|high|normal|low", "reason": "kisa aciklama"}'
        )

        response = await client.messages.create(
            model=settings.AI_MODEL_NAME,
            max_tokens=256,
            system="Sen bir satis email onceliklendirme asistanisin. Her emailin oncelik seviyesini belirle.",
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text if response.content else None
        if text:
            parsed = json.loads(text.strip())
            valid_priorities = {"urgent", "high", "normal", "low"}
            if parsed.get("priority") in valid_priorities:
                return {
                    "priority": parsed["priority"],
                    "reason": parsed.get("reason", "AI siniflandirma"),
                }
    except Exception as exc:
        logger.error("Claude triage hatasi: %s", exc)

    return None


def _rule_based_triage(email: EmailRequest, combined_text: str) -> dict:
    """Rule-based email priority classification."""
    reasons = []

    # Check urgent keywords
    urgent_matches = [kw for kw in URGENT_KEYWORDS if kw in combined_text]
    if urgent_matches:
        return {
            "priority": "urgent",
            "reason": f"Acil anahtar kelimeler tespit edildi: {', '.join(urgent_matches[:3])}",
        }

    # Check negative sentiment
    negative_matches = [kw for kw in NEGATIVE_SENTIMENT_KEYWORDS if kw in combined_text]
    if negative_matches:
        reasons.append(f"Olumsuz icerik: {', '.join(negative_matches[:3])}")

    # Check high priority keywords
    high_matches = [kw for kw in HIGH_PRIORITY_KEYWORDS if kw in combined_text]
    if high_matches:
        reasons.append(f"Onemli anahtar kelimeler: {', '.join(high_matches[:3])}")

    # Sentiment from classification
    if email.sentiment == "negative":
        reasons.append("Olumsuz duygu analizi")

    if negative_matches or (len(high_matches) >= 2) or email.sentiment == "negative":
        return {
            "priority": "high",
            "reason": "; ".join(reasons) if reasons else "Yuksek oncelik sinyalleri",
        }

    if high_matches:
        return {
            "priority": "normal",
            "reason": "; ".join(reasons) if reasons else "Standart is emali",
        }

    return {
        "priority": "low",
        "reason": "Acil veya onemli sinyal tespit edilmedi",
    }
