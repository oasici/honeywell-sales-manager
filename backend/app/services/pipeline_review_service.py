"""Pipeline review queue service (V9).

V2 Faz 3.0 backlog #4 — bulk stage update review queue. The AI
``suggest-pipeline-update`` endpoint already produces stage suggestions
per opportunity; V9 adds a *queue* so a manager can review/apply many
suggestions at once instead of clicking through each opp.

Public surface:
- ``list_pending_suggestions`` — un-decided suggestions, optionally
  scoped by owner_id
- ``propose`` — write a new suggestion row (idempotent — replaces
  the previous undecided suggestion for that opp+source)
- ``decide`` — apply or dismiss a suggestion
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity
from app.models.stage_config import StageConfig
from app.models.v9_board_ux import PipelineReviewQueueEntry

logger = logging.getLogger(__name__)


# ─────────────────────── pending list ────────────────────────────────


async def list_pending_suggestions(
    db: AsyncSession,
    *,
    owner_id: int | None = None,
    limit: int = 50,
) -> list[PipelineReviewQueueEntry]:
    stmt = (
        select(PipelineReviewQueueEntry)
        .join(Opportunity, Opportunity.id == PipelineReviewQueueEntry.opportunity_id)
        .where(PipelineReviewQueueEntry.decided_at.is_(None))
    )
    if owner_id is not None:
        stmt = stmt.where(Opportunity.owner_id == owner_id)
    stmt = stmt.order_by(PipelineReviewQueueEntry.suggested_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


# ─────────────────────── propose ─────────────────────────────────────


async def propose(
    db: AsyncSession,
    *,
    opportunity_id: int,
    suggested_stage: str | None = None,
    suggested_close_date: date | None = None,
    suggested_amount: float | None = None,
    suggestion_source: str = "rule",
    evidence: dict | None = None,
) -> PipelineReviewQueueEntry:
    """Write a new suggestion row.

    Replaces any *undecided* prior suggestion for the same
    (opportunity, source) so the queue doesn't bloat with stale
    proposals when the underlying signal flips.
    """
    existing = (
        await db.execute(
            select(PipelineReviewQueueEntry)
            .where(PipelineReviewQueueEntry.opportunity_id == opportunity_id)
            .where(PipelineReviewQueueEntry.suggestion_source == suggestion_source)
            .where(PipelineReviewQueueEntry.decided_at.is_(None))
        )
    ).scalar_one_or_none()

    payload_json = json.dumps(evidence or {}, ensure_ascii=False)

    if existing is not None:
        existing.suggested_stage = suggested_stage
        existing.suggested_close_date = suggested_close_date
        existing.suggested_amount = suggested_amount
        existing.evidence_json = payload_json
        existing.suggested_at = datetime.now(timezone.utc)
        await db.flush()
        return existing

    entry = PipelineReviewQueueEntry(
        opportunity_id=opportunity_id,
        suggested_stage=suggested_stage,
        suggested_close_date=suggested_close_date,
        suggested_amount=suggested_amount,
        suggestion_source=suggestion_source,
        evidence_json=payload_json,
    )
    db.add(entry)
    await db.flush()
    return entry


# ─────────────────────── decide (apply/dismiss) ──────────────────────


async def decide(
    db: AsyncSession,
    *,
    entry_id: int,
    decision: str,
    decided_by: int,
) -> PipelineReviewQueueEntry | None:
    """Apply or dismiss a queued suggestion.

    ``decision`` must be ``"applied"`` or ``"dismissed"``. On apply,
    the suggested fields land on the Opportunity; on dismiss we just
    record the decision.
    """
    if decision not in {"applied", "dismissed"}:
        raise ValueError("decision must be 'applied' or 'dismissed'")

    entry = await db.get(PipelineReviewQueueEntry, entry_id)
    if entry is None or entry.decided_at is not None:
        return entry

    if decision == "applied":
        opp = await db.get(Opportunity, entry.opportunity_id)
        if opp is not None:
            if entry.suggested_stage:
                opp.previous_stage = opp.stage
                opp.stage = entry.suggested_stage
            if entry.suggested_close_date is not None:
                opp.previous_close_date = opp.close_date
                opp.close_date = entry.suggested_close_date
            if entry.suggested_amount is not None:
                opp.previous_amount = opp.amount
                opp.amount = entry.suggested_amount

    entry.decision = decision
    entry.decided_by = decided_by
    entry.decided_at = datetime.now(timezone.utc)
    await db.flush()
    return entry


# ─────────────────────── WIP status ──────────────────────────────────


async def wip_status(db: AsyncSession) -> list[dict]:
    """Per-stage actual count vs. ``stage_configs.wip_limit``.

    Returns one row per stage with ``wip_warning=True`` when actual
    exceeds the limit. Stages without a limit are still returned so
    the UI can render the full board status in one call.
    """
    stages = (
        await db.execute(select(StageConfig).where(StageConfig.is_active.is_(True)))
    ).scalars().all()
    counts_rows = (
        await db.execute(
            select(Opportunity.stage, func.count(Opportunity.id))
            .where(Opportunity.status == "active")
            .group_by(Opportunity.stage)
        )
    ).all()
    by_stage = {str(r[0]): int(r[1]) for r in counts_rows}

    out = []
    for s in sorted(stages, key=lambda x: x.sort_order):
        actual = by_stage.get(s.stage_name, 0)
        limit = s.wip_limit
        out.append(
            {
                "stage_name": s.stage_name,
                "label": s.label,
                "actual": actual,
                "wip_limit": limit,
                "wip_warning": bool(limit is not None and actual > int(limit)),
                "headroom": (int(limit) - actual) if limit is not None else None,
            }
        )
    return out
