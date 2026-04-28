"""RAG backfill service (V11).

Pumps existing CRM data into the Qdrant collections that
``vector_store.py`` already manages. Used by:

- ``scripts/backfill_rag.py`` — manual one-off (idempotent)
- ``rag_incremental_backfill`` cron — nightly delta
- ``/api/v1/rag/reindex/{collection}`` — manager-triggered

Strategy
--------
Each backfill function is **idempotent**: vector_store builds point IDs
from a deterministic ``hashlib.md5`` of the entity id, so re-running
upserts overwrites the same point without duplicating.

All functions short-circuit when ``FEATURE_RAG=false`` so calling them
on a single-tenant deployment without Qdrant is harmless.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.competitor_mention import CompetitorMention
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.engagement import Transcript
from app.models.opportunity import Opportunity
from app.models.revenue_signal import RevenueSignal

logger = logging.getLogger(__name__)


@dataclass
class BackfillResult:
    deals_indexed: int = 0
    interactions_indexed: int = 0
    competitors_indexed: int = 0
    skipped: int = 0
    errors: int = 0


# ─────────────────────── deals ──────────────────────────────────────


async def backfill_deals(
    db: AsyncSession,
    *,
    since: datetime | None = None,
    limit: int = 1000,
) -> int:
    """Push opportunities to the deals collection.

    By default indexes everything; pass ``since`` for delta runs.
    Closed deals carry the most signal (outcome known) so we
    prioritise those, but active deals are useful too for "find
    similar in-flight deal" queries.
    """
    if not settings.FEATURE_RAG:
        return 0
    from app.services.vector_store import store_deal

    stmt = select(Opportunity, Customer).join(
        Customer, Customer.id == Opportunity.customer_id, isouter=True
    )
    if since is not None:
        stmt = stmt.where(Opportunity.updated_at >= since)
    stmt = stmt.order_by(Opportunity.updated_at.desc()).limit(limit)

    rows = (await db.execute(stmt)).all()
    indexed = 0
    for opp, cust in rows:
        try:
            risk = "low"
            if opp.stage == "closed_lost":
                risk = "high"
            elif opp.stage == "negotiation":
                risk = "medium"

            payload = {
                "id": int(opp.id),
                "title": opp.title or "",
                "stage": opp.stage,
                "amount": float(opp.amount or 0.0),
                "outcome": "won" if opp.stage == "closed_won" else "lost" if opp.stage == "closed_lost" else "active",
                "risk_level": risk,
                "customer_name": (cust.name if cust else "") or "",
                "summary": opp.title or "",
                "signal_summary": opp.loss_reason or "",
            }
            point_id = await store_deal(payload)
            if point_id:
                indexed += 1
        except Exception as exc:
            logger.warning("backfill_deals: opp=%s err=%s", opp.id, exc)
    logger.info("backfill_deals: indexed=%s rows_seen=%s", indexed, len(rows))
    return indexed


# ─────────────────────── interactions ───────────────────────────────


async def backfill_interactions(
    db: AsyncSession,
    *,
    since: datetime | None = None,
    limit: int = 2000,
) -> int:
    """Push transcripts + emails into the interactions collection.

    Source priority:
      1. Transcripts — richest signal (already summarised)
      2. EmailRequests with parsed_data.body
    """
    if not settings.FEATURE_RAG:
        return 0
    from app.services.vector_store import store_interaction

    indexed = 0

    # Transcripts ───────────────────────────────────────────────
    stmt = select(Transcript)
    if since is not None:
        stmt = stmt.where(Transcript.created_at >= since)
    stmt = stmt.order_by(Transcript.created_at.desc()).limit(limit)
    transcripts = (await db.execute(stmt)).scalars().all()
    for tr in transcripts:
        try:
            content = (tr.summary or "") + "\n" + (tr.content or "")
            if not content.strip():
                continue
            payload = {
                "id": int(tr.id),
                "type": "transcript",
                "customer_id": getattr(tr, "customer_id", None),
                "opportunity_id": getattr(tr, "opportunity_id", None),
                "sentiment": tr.sentiment or "neutral",
                "content": content,
            }
            point_id = await store_interaction(payload)
            if point_id:
                indexed += 1
        except Exception as exc:
            logger.warning("backfill_interactions: transcript=%s err=%s", tr.id, exc)

    # Emails ────────────────────────────────────────────────────
    stmt = select(EmailRequest)
    if since is not None:
        stmt = stmt.where(EmailRequest.created_at >= since)
    stmt = stmt.order_by(EmailRequest.created_at.desc()).limit(limit)
    emails = (await db.execute(stmt)).scalars().all()
    for em in emails:
        try:
            body = (
                getattr(em, "raw_text", None)
                or getattr(em, "body", None)
                or getattr(em, "subject", None)
                or ""
            )
            if not body.strip():
                continue
            payload = {
                "id": int(em.id),
                "type": "email",
                "customer_id": getattr(em, "customer_id", None),
                "opportunity_id": getattr(em, "opportunity_id", None),
                "sentiment": "neutral",
                "content": body,
            }
            point_id = await store_interaction(payload)
            if point_id:
                indexed += 1
        except Exception as exc:
            logger.warning("backfill_interactions: email=%s err=%s", em.id, exc)

    logger.info(
        "backfill_interactions: indexed=%s transcripts=%s emails=%s",
        indexed,
        len(transcripts),
        len(emails),
    )
    return indexed


# ─────────────────────── competitors ────────────────────────────────


async def backfill_competitors(
    db: AsyncSession,
    *,
    since: datetime | None = None,
    limit: int = 2000,
) -> int:
    """Push competitor_mentions + competitor RevenueSignals to vector store."""
    if not settings.FEATURE_RAG:
        return 0
    from app.services.vector_store import store_competitor_intel

    indexed = 0

    stmt = select(CompetitorMention)
    if since is not None:
        stmt = stmt.where(CompetitorMention.created_at >= since)
    stmt = stmt.order_by(CompetitorMention.created_at.desc()).limit(limit)
    mentions = (await db.execute(stmt)).scalars().all()
    for cm in mentions:
        try:
            payload = {
                "competitor": cm.competitor_name,
                "source": cm.source_entity_type or "internal",
                "source_url": "",
                "content": cm.context_snippet or "",
                "category": "internal_mention",
                "date": cm.created_at.date().isoformat() if cm.created_at else "",
            }
            point_id = await store_competitor_intel(payload)
            if point_id:
                indexed += 1
        except Exception as exc:
            logger.warning("backfill_competitors: mention=%s err=%s", cm.id, exc)

    # Also walk RevenueSignals tagged competitor_mention/objection/competition
    stmt2 = select(RevenueSignal).where(
        RevenueSignal.signal_type.in_(["competitor_mention", "competition"])
    )
    if since is not None:
        stmt2 = stmt2.where(RevenueSignal.created_at >= since)
    stmt2 = stmt2.order_by(RevenueSignal.created_at.desc()).limit(limit)
    signals = (await db.execute(stmt2)).scalars().all()
    for sig in signals:
        try:
            payload = {
                "competitor": "unspecified",
                "source": sig.source_entity_type or "signal",
                "source_url": "",
                "content": sig.recommended_action or "",
                "category": "revenue_signal",
                "date": sig.created_at.date().isoformat() if sig.created_at else "",
            }
            point_id = await store_competitor_intel(payload)
            if point_id:
                indexed += 1
        except Exception as exc:
            logger.warning("backfill_competitors: signal=%s err=%s", sig.id, exc)

    logger.info(
        "backfill_competitors: indexed=%s mentions=%s signals=%s",
        indexed,
        len(mentions),
        len(signals),
    )
    return indexed


# ─────────────────────── orchestrator ───────────────────────────────


async def run_full_backfill(
    db: AsyncSession,
    *,
    since: datetime | None = None,
) -> BackfillResult:
    """Run all 3 backfills sequentially. Used by cron + manual trigger."""
    result = BackfillResult()
    if not settings.FEATURE_RAG:
        logger.info("FEATURE_RAG=false, skipping RAG backfill")
        return result
    result.deals_indexed = await backfill_deals(db, since=since)
    result.interactions_indexed = await backfill_interactions(db, since=since)
    result.competitors_indexed = await backfill_competitors(db, since=since)
    return result


async def run_incremental_backfill(db: AsyncSession) -> BackfillResult:
    """Cron-friendly delta — last 25 hours of changes (1h overlap)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=25)
    return await run_full_backfill(db, since=cutoff)


# ─────────────────────── inline auto-ingest hooks ───────────────────


async def index_transcript_now(transcript_id: int) -> None:
    """Best-effort hook used after transcript creation — non-blocking."""
    if not settings.FEATURE_RAG:
        return
    from app.core.database import async_session
    from app.services.vector_store import store_interaction

    async with async_session() as db:
        tr = await db.get(Transcript, transcript_id)
        if tr is None:
            return
        content = (tr.summary or "") + "\n" + (tr.content or "")
        if not content.strip():
            return
        try:
            await store_interaction(
                {
                    "id": int(tr.id),
                    "type": "transcript",
                    "customer_id": getattr(tr, "customer_id", None),
                    "opportunity_id": getattr(tr, "opportunity_id", None),
                    "sentiment": tr.sentiment or "neutral",
                    "content": content,
                }
            )
        except Exception as exc:
            logger.warning("index_transcript_now failed: %s", exc)


async def index_opportunity_close(opportunity_id: int) -> None:
    """Hook fired when an Opportunity hits closed_won/closed_lost."""
    if not settings.FEATURE_RAG:
        return
    from app.core.database import async_session
    from app.services.vector_store import store_deal

    async with async_session() as db:
        opp = await db.get(Opportunity, opportunity_id)
        if opp is None or opp.stage not in {"closed_won", "closed_lost"}:
            return
        cust = (
            await db.execute(
                select(Customer).where(Customer.id == opp.customer_id)
            )
        ).scalar_one_or_none() if opp.customer_id else None
        try:
            await store_deal(
                {
                    "id": int(opp.id),
                    "title": opp.title or "",
                    "stage": opp.stage,
                    "amount": float(opp.amount or 0.0),
                    "outcome": "won" if opp.stage == "closed_won" else "lost",
                    "risk_level": "high" if opp.stage == "closed_lost" else "low",
                    "customer_name": (cust.name if cust else "") or "",
                    "summary": opp.title or "",
                    "signal_summary": opp.loss_reason or "",
                }
            )
        except Exception as exc:
            logger.warning("index_opportunity_close failed: %s", exc)
