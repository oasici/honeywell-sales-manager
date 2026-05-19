"""Materialize ``v4_deal_replay_snapshots`` from the additive normalized timeline (+ optional OFD row)."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.additive.timeline_query import load_merged_canonical_timeline
from app.models.deal_replay_snapshot import DealReplaySnapshot
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity

REPLAY_MODEL_VERSION = "v4-deal-replay-mvp-1"


async def materialize_deal_replay_snapshot(
    db: AsyncSession,
    opportunity_id: int,
    snapshot_date: date,
    *,
    timeline_limit: int = 500,
    include_signals: bool = True,
    include_legacy_opportunity_signals: bool = True,
) -> DealReplaySnapshot:
    """Upsert one snapshot row for ``(opportunity_id, snapshot_date)``."""
    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == opportunity_id))
    ).scalar_one_or_none()
    if not opp:
        raise ValueError("opportunity_not_found")

    account_id = int(opp.customer_id) if opp.customer_id else None

    merged = await load_merged_canonical_timeline(
        db,
        opportunity_id,
        account_id=account_id,
        limit=timeline_limit,
        include_signals=include_signals,
        include_legacy_opportunity_signals=include_legacy_opportunity_signals,
    )

    ofd = (
        await db.execute(
            select(OpportunityFeaturesDaily).where(
                OpportunityFeaturesDaily.opportunity_id == opportunity_id,
                OpportunityFeaturesDaily.snapshot_date == snapshot_date,
            )
        )
    ).scalar_one_or_none()

    meta: dict = {
        "replay_model_version": REPLAY_MODEL_VERSION,
        "source_timeline_version": "v4-additive-readmodel",
        "timeline_item_count": len(merged),
        "include_signals": include_signals,
        "include_legacy_opportunity_signals": include_legacy_opportunity_signals,
        "feature_daily_present": ofd is not None,
    }
    if ofd:
        meta["feature_daily"] = {
            "momentum_band": ofd.momentum_band,
            "momentum_score": ofd.momentum_score,
            "buyer_state": ofd.buyer_state,
            "close_probability": ofd.close_probability,
        }

    frames_obj = {
        "replay_model_version": REPLAY_MODEL_VERSION,
        "include_signals": include_signals,
        "include_legacy_opportunity_signals": include_legacy_opportunity_signals,
        "items": [m.model_dump() for m in merged],
    }

    now = datetime.now(timezone.utc)
    frames_json = json.dumps(frames_obj, default=str)
    meta_json = json.dumps(meta, default=str)

    existing = (
        await db.execute(
            select(DealReplaySnapshot).where(
                DealReplaySnapshot.opportunity_id == opportunity_id,
                DealReplaySnapshot.snapshot_date == snapshot_date,
            )
        )
    ).scalar_one_or_none()

    if existing:
        existing.frames_json = frames_json
        existing.meta_json = meta_json
        existing.source_timeline_version = "v4-additive-readmodel"
        existing.updated_at = now
        await db.flush()
        return existing

    row = DealReplaySnapshot(
        opportunity_id=opportunity_id,
        # Round-15 Sprint 15n cohort 4 — tenant_id NOT NULL. Mirror the
        # parent opportunity (NOT NULL since cohort 1).
        tenant_id=opp.tenant_id,
        snapshot_date=snapshot_date,
        frames_json=frames_json,
        meta_json=meta_json,
        source_timeline_version="v4-additive-readmodel",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    await db.flush()
    return row
