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
