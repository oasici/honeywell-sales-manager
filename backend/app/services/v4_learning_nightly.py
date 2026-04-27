"""Nightly DNA + deal replay batch (quota-limited, UTC yesterday snapshot date)."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.activity_log import ActivityLog
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity

logger = logging.getLogger(__name__)


def utc_yesterday() -> date:
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=1)).date()


async def collect_active_opportunity_ids(
    db: AsyncSession,
    target_date: date,
    *,
    lookback_days: int = 7,
    limit: int,
) -> list[int]:
    """Active opportunities with OFD row for ``target_date`` or activity in ``lookback_days`` before EOD."""
    end = datetime.combine(target_date, time(23, 59, 59), tzinfo=timezone.utc)
    start = end - timedelta(days=lookback_days)

    ofd_ids = set(
        (
            await db.execute(
                select(OpportunityFeaturesDaily.opportunity_id)
                .join(Opportunity, Opportunity.id == OpportunityFeaturesDaily.opportunity_id)
                .where(
                    OpportunityFeaturesDaily.snapshot_date == target_date,
                    Opportunity.status == "active",
                )
                .distinct()
            )
        ).scalars().all()
    )

    act_ids = set(
        (
            await db.execute(
                select(ActivityLog.opportunity_id)
                .join(Opportunity, Opportunity.id == ActivityLog.opportunity_id)
                .where(
                    ActivityLog.opportunity_id.isnot(None),
                    Opportunity.status == "active",
                    ActivityLog.created_at >= start,
                    ActivityLog.created_at <= end,
                )
                .distinct()
                .limit(max(limit * 4, limit))
            )
        ).scalars().all()
    )

    merged = sorted(ofd_ids | act_ids)[: max(1, limit)]
    return merged


async def run_v4_sales_dna_nightly(
    db: AsyncSession,
    target_date: date | None = None,
) -> dict[str, int | str]:
    from app.services.sales_dna_service import materialize_sales_dna_snapshot

    target = target_date or utc_yesterday()
    cap = max(1, int(settings.V4_SALES_DNA_NIGHTLY_MAX_OPPORTUNITIES))
    ids = await collect_active_opportunity_ids(db, target, limit=cap)
    ok, fail = 0, 0
    for oid in ids:
        try:
            await materialize_sales_dna_snapshot(db, oid, target)
            await db.commit()
            ok += 1
        except Exception as exc:
            await db.rollback()
            fail += 1
            logger.warning("v4_sales_dna_nightly skip opp=%s: %s", oid, exc)
    logger.info(
        "v4_sales_dna_nightly done date=%s processed=%s failed=%s cap=%s",
        target,
        ok,
        fail,
        cap,
    )
    return {"snapshot_date": str(target), "processed": ok, "failed": fail, "capped_at": cap}


async def run_v4_deal_replay_nightly(
    db: AsyncSession,
    target_date: date | None = None,
) -> dict[str, int | str]:
    from app.services.deal_replay_snapshot_service import materialize_deal_replay_snapshot

    target = target_date or utc_yesterday()
    cap = max(1, int(settings.V4_DEAL_REPLAY_NIGHTLY_MAX_OPPORTUNITIES))
    ids = await collect_active_opportunity_ids(db, target, limit=cap)
    ok, fail = 0, 0
    for oid in ids:
        try:
            await materialize_deal_replay_snapshot(
                db,
                oid,
                target,
                timeline_limit=400,
                include_signals=True,
                include_legacy_opportunity_signals=True,
            )
            await db.commit()
            ok += 1
        except Exception as exc:
            await db.rollback()
            fail += 1
            logger.warning("v4_deal_replay_nightly skip opp=%s: %s", oid, exc)
    logger.info(
        "v4_deal_replay_nightly done date=%s processed=%s failed=%s cap=%s",
        target,
        ok,
        fail,
        cap,
    )
    return {"snapshot_date": str(target), "processed": ok, "failed": fail, "capped_at": cap}


async def run_v5_intelligence_nightly(
    db: AsyncSession,
    target_date: date | None = None,
) -> dict[str, int | str]:
    """V5 nightly: foundation augmentation → mine objections/DNA → similarity → rep DNA → anomaly scan.

    Each step commits independently and best-efforts the next; one
    failing service should not poison the entire run.
    """
    from app.services.benchmark_gap_service import scan_anomalies
    from app.services.deal_similarity_service import (
        refresh_similarity_links,
        upsert_embedding,
    )
    from app.services.dna_pattern_miner import mine_patterns
    from app.services.objection_intelligence_service import refresh_patterns as refresh_objection_patterns
    from app.services.rep_dna_service import refresh_all_rep_dna
    from app.services.timing_engine_service import materialize_windows_for_opportunity
    from app.services.v5_foundation_builder import run_v5_foundation_augmentation

    target = target_date or utc_yesterday()
    cap = max(1, int(settings.V5_NIGHTLY_MAX_OPPORTUNITIES))
    ids = await collect_active_opportunity_ids(db, target, limit=cap)

    counters: dict[str, int] = {
        "foundation_accounts": 0,
        "foundation_reps": 0,
        "objection_patterns": 0,
        "dna_patterns": 0,
        "embeddings": 0,
        "similarity_links": 0,
        "timing_windows": 0,
        "rep_dna": 0,
        "anomalies": 0,
        "failed_opportunities": 0,
    }

    # 1) Foundation augmentation (account + rep V5 columns).
    try:
        result = await run_v5_foundation_augmentation(db, snapshot_date=target)
        counters["foundation_accounts"] = result.accounts_updated
        counters["foundation_reps"] = result.reps_updated
    except Exception as exc:
        await db.rollback()
        logger.warning("v5_foundation_augmentation failed: %s", exc)

    # 2) Per-opportunity work: embeddings, timing windows.
    for oid in ids:
        try:
            emb = await upsert_embedding(db, opportunity_id=oid)
            if emb is not None:
                counters["embeddings"] += 1
            counters["timing_windows"] += await materialize_windows_for_opportunity(
                db, opportunity_id=oid
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            counters["failed_opportunities"] += 1
            logger.warning("v5_per_opp skip opp=%s: %s", oid, exc)

    # 3) Similarity links — needs embeddings written first.
    for oid in ids:
        try:
            counters["similarity_links"] += await refresh_similarity_links(
                db, opportunity_id=oid
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.warning("v5_similarity skip opp=%s: %s", oid, exc)

    # 4) Segment-level miners (cheap globally, run once).
    try:
        counters["objection_patterns"] = await refresh_objection_patterns(db)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("v5_objection_patterns failed: %s", exc)

    try:
        counters["dna_patterns"] = await mine_patterns(db)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("v5_dna_patterns failed: %s", exc)

    try:
        counters["rep_dna"] = await refresh_all_rep_dna(db, snapshot_date=target)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("v5_rep_dna failed: %s", exc)

    try:
        counters["anomalies"] = await scan_anomalies(db)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.warning("v5_anomaly_scan failed: %s", exc)

    logger.info(
        "v5_intelligence_nightly done date=%s opps=%s counters=%s",
        target,
        len(ids),
        counters,
    )
    return {"snapshot_date": str(target), "opportunities": len(ids), **counters}
