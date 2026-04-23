"""Competitive intelligence — scan text for competitor mentions and aggregate insights."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.competitor_mention import CompetitorMention

logger = logging.getLogger(__name__)

KNOWN_COMPETITORS = [
    "Siemens",
    "ABB",
    "Schneider",
    "Emerson",
    "Yokogawa",
    "Danfoss",
    "Carrier",
]

SNIPPET_CONTEXT_CHARS = 100


async def scan_for_competitors(
    db: AsyncSession,
    text: str,
    source_type: str,
    source_id: int,
    opportunity_id: int | None = None,
) -> list[dict]:
    """Scan text for competitor mentions. Uses keyword list + optional AI.

    Returns list of detected mentions.
    """
    mentions = []

    # Strategy 1: Keyword-based detection (always runs)
    keyword_mentions = _keyword_scan(text, source_type, source_id, opportunity_id)
    mentions.extend(keyword_mentions)

    # Strategy 2: AI-enhanced detection (if API key available)
    if settings.ANTHROPIC_API_KEY:
        ai_mentions = await _ai_scan(text, source_type, source_id, opportunity_id)
        if ai_mentions:
            # Deduplicate: skip AI mentions for competitors already found by keyword
            found_names = {m["competitor_name"].lower() for m in mentions}
            for m in ai_mentions:
                if m["competitor_name"].lower() not in found_names:
                    mentions.append(m)
                    found_names.add(m["competitor_name"].lower())

    # Persist mentions
    for mention_data in mentions:
        mention = CompetitorMention(
            competitor_name=mention_data["competitor_name"],
            source_entity_type=mention_data["source_entity_type"],
            source_entity_id=mention_data["source_entity_id"],
            opportunity_id=mention_data.get("opportunity_id"),
            context_snippet=mention_data.get("context_snippet"),
            sentiment=mention_data.get("sentiment", "neutral"),
            detected_by=mention_data.get("detected_by", "keyword"),
        )
        db.add(mention)

    if mentions:
        await db.flush()

    return mentions


def _keyword_scan(
    text: str,
    source_type: str,
    source_id: int,
    opportunity_id: int | None,
) -> list[dict]:
    """Scan text for known competitor names."""
    text_lower = text.lower()
    found = []

    for competitor in KNOWN_COMPETITORS:
        idx = text_lower.find(competitor.lower())
        if idx == -1:
            continue

        # Extract context snippet
        start = max(0, idx - SNIPPET_CONTEXT_CHARS)
        end = min(len(text), idx + len(competitor) + SNIPPET_CONTEXT_CHARS)
        snippet = text[start:end]
        if start > 0:
            snippet = "..." + snippet
        if end < len(text):
            snippet = snippet + "..."

        found.append({
            "competitor_name": competitor,
            "source_entity_type": source_type,
            "source_entity_id": source_id,
            "opportunity_id": opportunity_id,
            "context_snippet": snippet,
            "sentiment": "neutral",
            "detected_by": "keyword",
        })

    return found


async def _ai_scan(
    text: str,
    source_type: str,
    source_id: int,
    opportunity_id: int | None,
) -> list[dict] | None:
    """Use Claude to detect competitor mentions with sentiment."""
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

        prompt = (
            "Asagidaki metinde rakip firma bahislerini tespit et.\n"
            f"Bilinen rakipler: {', '.join(KNOWN_COMPETITORS)}\n"
            "Baska rakipler de olabilir.\n\n"
            f"Metin:\n{text[:4000]}\n\n"
            "JSON array formatinda cevap ver:\n"
            '[{"competitor_name": "...", "sentiment": "positive|neutral|negative", '
            '"context_snippet": "ilgili cumle"}]\n'
            "Hicbir rakip yoksa bos array don: []"
        )

        response = await client.messages.create(
            model=settings.AI_MODEL_NAME,
            max_tokens=512,
            system="Sen bir rekabet analiz asistanisin. Metinlerde rakip firma bahislerini tespit et.",
            messages=[{"role": "user", "content": prompt}],
        )

        ai_text = response.content[0].text if response.content else None
        if ai_text:
            parsed = json.loads(ai_text.strip())
            if isinstance(parsed, list):
                return [
                    {
                        "competitor_name": m.get("competitor_name", ""),
                        "source_entity_type": source_type,
                        "source_entity_id": source_id,
                        "opportunity_id": opportunity_id,
                        "context_snippet": m.get("context_snippet", ""),
                        "sentiment": m.get("sentiment", "neutral"),
                        "detected_by": "ai",
                    }
                    for m in parsed
                    if m.get("competitor_name")
                ]
    except Exception as exc:
        logger.error("Claude rekabet analizi hatasi: %s", exc)

    return None


async def get_competitor_dashboard(db: AsyncSession, days: int = 90) -> dict:
    """Aggregate: mentions by competitor with sentiment and recent mentions.

    Returns shape expected by frontend CompetitiveIntelData:
    {competitors: [{name, mention_count, sentiment_avg, recent_mentions}], total_mentions}
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # NOTE: In some deployments this table may not exist yet (partial migrations,
    # read-only replicas, etc.). The cockpit should degrade gracefully.
    try:
        # Mentions by competitor with sentiment stats
        by_competitor_result = await db.execute(
            select(
                CompetitorMention.competitor_name,
                func.count(CompetitorMention.id).label("mention_count"),
            )
            .where(CompetitorMention.created_at >= cutoff)
            .group_by(CompetitorMention.competitor_name)
            .order_by(func.count(CompetitorMention.id).desc())
        )
        competitor_names = [
            {"name": row[0], "mention_count": row[1]} for row in by_competitor_result.all()
        ]

        # Sentiment breakdown per competitor
        sentiment_result = await db.execute(
            select(
                CompetitorMention.competitor_name,
                CompetitorMention.sentiment,
                func.count(CompetitorMention.id).label("count"),
            )
            .where(CompetitorMention.created_at >= cutoff)
            .group_by(CompetitorMention.competitor_name, CompetitorMention.sentiment)
        )
        sentiment_map: dict[str, dict[str, int]] = {}
        for row in sentiment_result.all():
            comp = row[0]
            sent = row[1] or "neutral"
            cnt = row[2]
            if comp not in sentiment_map:
                sentiment_map[comp] = {"positive": 0, "neutral": 0, "negative": 0}
            sentiment_map[comp][sent] = cnt

        # Recent mentions per competitor (latest 5)
        recent_map: dict[str, list[dict]] = {}
        for comp_data in competitor_names:
            comp_name = comp_data["name"]
            recent_result = await db.execute(
                select(CompetitorMention)
                .where(
                    CompetitorMention.competitor_name == comp_name,
                    CompetitorMention.created_at >= cutoff,
                )
                .order_by(CompetitorMention.created_at.desc())
                .limit(5)
            )
            recent_map[comp_name] = [
                {
                    "source_type": m.source_entity_type,
                    "context_snippet": m.context_snippet or "",
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in recent_result.scalars().all()
            ]

        # Build response matching frontend CompetitiveIntelData
        SENTIMENT_SCORES = {"positive": 1.0, "neutral": 0.0, "negative": -1.0}
        competitors = []
        for comp_data in competitor_names:
            name = comp_data["name"]
            sentiments = sentiment_map.get(name, {"positive": 0, "neutral": 0, "negative": 0})
            total_sent = sum(sentiments.values()) or 1
            sentiment_avg = (
                sum(SENTIMENT_SCORES.get(k, 0) * v for k, v in sentiments.items())
                / total_sent
            )

            competitors.append(
                {
                    "name": name,
                    "mention_count": comp_data["mention_count"],
                    "sentiment_avg": round(sentiment_avg, 2),
                    "recent_mentions": recent_map.get(name, []),
                }
            )

        # Total mentions
        total = (
            await db.execute(
                select(func.count(CompetitorMention.id)).where(
                    CompetitorMention.created_at >= cutoff
                )
            )
        ).scalar() or 0

        return {"competitors": competitors, "total_mentions": total}
    except Exception as exc:
        logger.warning("Competitive intel dashboard unavailable: %s", exc)
        return {"competitors": [], "total_mentions": 0}
