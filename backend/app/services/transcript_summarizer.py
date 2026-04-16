"""Transcript summarizer — extract summaries, action items, sentiment via Claude or fallback."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.engagement import Transcript

logger = logging.getLogger(__name__)

CONTEXT_MAX_CHARS = 8000


async def summarize_transcript(db: AsyncSession, transcript_id: int) -> dict:
    """Summarize transcript via Claude. Extract action items, sentiment, key topics.

    Returns {summary, action_items: [], sentiment, key_topics: []}.
    """
    transcript = (
        await db.execute(select(Transcript).where(Transcript.id == transcript_id))
    ).scalar_one_or_none()

    if not transcript:
        return {"error": "Transkript bulunamadi"}

    content = transcript.content or ""

    # Strategy 1: Claude AI summarization
    if settings.ANTHROPIC_API_KEY:
        ai_result = await _claude_summarize(transcript, content)
        if ai_result:
            transcript.summary = ai_result["summary"]
            transcript.action_items_json = json.dumps(
                ai_result["action_items"], ensure_ascii=False
            )
            transcript.sentiment = ai_result["sentiment"]
            await db.flush()
            return ai_result

    # Strategy 2: Rule-based fallback
    result = _rule_based_summarize(transcript, content)
    transcript.summary = result["summary"]
    transcript.action_items_json = json.dumps(
        result["action_items"], ensure_ascii=False
    )
    transcript.sentiment = result["sentiment"]
    await db.flush()
    return result


async def _claude_summarize(transcript: Transcript, content: str) -> dict | None:
    """Use Claude to summarize transcript."""
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = (
            f"Baslik: {transcript.title}\n"
            f"Kaynak: {transcript.source}\n"
            f"Sure: {transcript.duration_minutes or 'Bilinmiyor'} dakika\n"
            f"Katilimcilar: {transcript.participants or 'Bilinmiyor'}\n\n"
            f"Transkript (ilk {CONTEXT_MAX_CHARS} karakter):\n"
            f"{content[:CONTEXT_MAX_CHARS]}\n\n"
            "JSON formatinda cevap ver:\n"
            '{"summary": "3-5 cumlelik ozet", '
            '"action_items": ["aksiyon 1", "aksiyon 2"], '
            '"sentiment": "positive|neutral|negative", '
            '"key_topics": ["konu 1", "konu 2"]}'
        )

        response = await client.messages.create(
            model=settings.AI_MODEL_NAME,
            max_tokens=512,
            system=(
                "Sen bir satis gorusme ozet asistanisin. Turkce, kisa ve "
                "aksiyona yonelik ozetler uret. Onemli kararlari ve aksiyon "
                "maddelerini cikar."
            ),
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text if response.content else None
        if text:
            parsed = json.loads(text.strip())
            valid_sentiments = {"positive", "neutral", "negative"}
            return {
                "transcript_id": transcript.id,
                "summary": parsed.get("summary", ""),
                "action_items": parsed.get("action_items", []),
                "sentiment": (
                    parsed["sentiment"]
                    if parsed.get("sentiment") in valid_sentiments
                    else "neutral"
                ),
                "key_topics": parsed.get("key_topics", []),
                "method": "ai",
            }
    except Exception as exc:
        logger.error("Claude transkript ozet hatasi: %s", exc)

    return None


def _rule_based_summarize(transcript: Transcript, content: str) -> dict:
    """Rule-based transcript summarization fallback."""
    sentences = [s.strip() for s in content.replace("!", ".").replace("?", ".").split(".") if s.strip()]

    # Take first few sentences as summary
    summary_sentences = sentences[:5] if len(sentences) >= 5 else sentences
    summary = ". ".join(summary_sentences) + "." if summary_sentences else "Ozet olusturulamadi."

    # Extract action items (look for action-like patterns)
    action_keywords = [
        "yapilacak", "gonderilecek", "hazirlanacak", "aranacak",
        "planlanacak", "kontrol edilecek", "takip", "follow up",
        "todo", "action", "yapmaliyiz", "gondermeliyiz",
    ]
    action_items = []
    content_lower = content.lower()
    for sentence in sentences:
        if any(kw in sentence.lower() for kw in action_keywords):
            action_items.append(sentence)
    action_items = action_items[:5]

    # Simple sentiment detection
    positive_words = ["memnun", "guzel", "basarili", "iyi", "harika", "mukemmel", "olumlu"]
    negative_words = ["sorun", "sikinti", "problem", "gecikme", "sikayet", "olumsuz", "kotu"]

    positive_count = sum(1 for w in positive_words if w in content_lower)
    negative_count = sum(1 for w in negative_words if w in content_lower)

    if positive_count > negative_count:
        sentiment = "positive"
    elif negative_count > positive_count:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    # Extract key topics (most frequent significant words)
    key_topics = _extract_key_topics(content)

    return {
        "transcript_id": transcript.id,
        "summary": summary[:500],
        "action_items": action_items,
        "sentiment": sentiment,
        "key_topics": key_topics,
        "method": "rule_based",
    }


def _extract_key_topics(content: str) -> list[str]:
    """Extract key topics from content based on word frequency."""
    stop_words = {
        "bir", "bu", "su", "ve", "ile", "icin", "olan", "var", "yok",
        "ben", "sen", "biz", "siz", "ama", "fakat", "cunku", "eger",
        "the", "and", "for", "with", "this", "that", "from", "are",
    }
    words = content.lower().split()
    word_counts: dict[str, int] = {}
    for word in words:
        cleaned = word.strip(".,;:!?()[]\"'")
        if len(cleaned) > 3 and cleaned not in stop_words:
            word_counts[cleaned] = word_counts.get(cleaned, 0) + 1

    sorted_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)
    return [word for word, _ in sorted_words[:5]]
