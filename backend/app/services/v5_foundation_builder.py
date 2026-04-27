"""V5 foundation feature builders.

Extends ``feature_store_builder`` with the V5 columns on
``account_features_daily`` and ``rep_features_daily``. Kept in a
separate module so the V4 builder stays unchanged and either pipeline
can be switched on/off independently.

Design
------
We do NOT recompute the V4 columns here — those land via
``feature_store_builder.build_daily_feature_store``. Instead we
**augment** existing rows for the same ``snapshot_date`` with the V5
metrics:

* AccountFeaturesDaily
  - ``avg_momentum``: mean of OFD ``momentum_score`` over the account's
    open opportunities for the day.
  - ``stakeholder_coverage_avg``: mean stakeholder count per opp.
  - ``buyer_engagement_score``: 0..100 derived from buyer reply +
    meeting rhythm.
  - ``objection_density_30d``: count of unresolved objections / open
    opp count (>=1 baseline).
  - ``expansion_signal_score``: positive_signal counts over 14d.

* RepFeaturesDaily
  - ``objection_recovery_rate``: resolved objections / total
    objections seen on this rep's deals (lookback 90d).
  - ``sequence_adherence_rate``: stub @ 0 until sequence_v2 wiring
    matures (interface stable; we just leave it None when no data).
  - ``stage_slippage_rate``: count of opps that moved backward in
    stage / total stage transitions in 90d.
  - ``discount_dependence``: avg ``latest_discount_pct`` across won
    deals in 90d.
  - ``sample_deals``: count of deals contributing to the metrics.

All math is best-effort — when a denominator is zero we leave the
column ``None`` (not ``0.0``) so the UI can render "no data yet" vs
"genuinely zero".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_store_daily import (
    AccountFeaturesDaily,
    OpportunityFeaturesDaily,
    RepFeaturesDaily,
)
from app.models.opportunity import Opportunity
from app.models.sequence_v2 import Stakeholder
from app.models.v5_objection import Objection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class V5BuildResult:
    snapshot_date: date
    accounts_updated: int
    reps_updated: int


def _safe_mean(values: list[float]) -> float | None:
    return (sum(values) / len(values)) if values else None


# ─────────────────────── account-level V5 augmentation ──────────────────


async def augment_account_features_daily(
    db: AsyncSession, *, snapshot_date: date
) -> int:
    """Populate V5 columns on ``account_features_daily`` for ``snapshot_date``.

    Reads the OFD rows already produced by the V4 builder and rolls
    them up to the account level. Returns the number of rows updated.
    """
    rows = (
        await db.execute(
            select(AccountFeaturesDaily).where(
                AccountFeaturesDaily.snapshot_date == snapshot_date
            )
        )
    ).scalars().all()
    if not rows:
        return 0

    # Pull every OFD row for this snapshot in one query, plus the
    # opportunity → customer mapping. Keeps the loop O(1) on DB hits.
    ofd_rows = (
        await db.execute(
            select(OpportunityFeaturesDaily, Opportunity)
            .join(Opportunity, Opportunity.id == OpportunityFeaturesDaily.opportunity_id)
            .where(OpportunityFeaturesDaily.snapshot_date == snapshot_date)
            .where(Opportunity.status == "active")
        )
    ).all()

    by_account: dict[int, list[OpportunityFeaturesDaily]] = {}
    by_account_opps: dict[int, list[Opportunity]] = {}
    for ofd, opp in ofd_rows:
        if opp.customer_id is None:
            continue
        cid = int(opp.customer_id)
        by_account.setdefault(cid, []).append(ofd)
        by_account_opps.setdefault(cid, []).append(opp)

    # Stakeholder count per opportunity (single batched query)
    sh_count_rows = (
        await db.execute(
            select(Stakeholder.opportunity_id, func.count(Stakeholder.id))
            .where(Stakeholder.opportunity_id.isnot(None))
            .group_by(Stakeholder.opportunity_id)
        )
    ).all()
    sh_by_opp = {int(r[0]): int(r[1]) for r in sh_count_rows if r[0] is not None}

    # Unresolved objections in last 30d, grouped by account.
    since_30d = datetime.now(timezone.utc) - timedelta(days=30)
    obj_rows = (
        await db.execute(
            select(Objection, Opportunity)
            .join(Opportunity, Opportunity.id == Objection.opportunity_id)
            .where(Objection.created_at >= since_30d)
            .where(Objection.resolved_flag.is_(False))
        )
    ).all()
    obj_count_by_account: dict[int, int] = {}
    for _obj, opp in obj_rows:
        if opp.customer_id is None:
            continue
        cid = int(opp.customer_id)
        obj_count_by_account[cid] = obj_count_by_account.get(cid, 0) + 1

    updated = 0
    for row in rows:
        cid = int(row.account_id)
        ofds = by_account.get(cid, [])
        if not ofds:
            # No active opps for this account today — V5 columns stay
            # null and we still bump expansion_signal_score=0 so the
            # column has a defined value for the dashboard.
            row.expansion_signal_score = 0.0
            continue

        momenta = [float(o.momentum_score) for o in ofds if o.momentum_score is not None]
        row.avg_momentum = _safe_mean(momenta)

        sh_counts = [
            float(sh_by_opp.get(int(o.opportunity_id), 0)) for o in ofds
        ]
        row.stakeholder_coverage_avg = _safe_mean(sh_counts)

        # Buyer engagement: replies + meetings normalized to 0..100. We
        # use 14d windows already pre-computed on OFD.
        replies = [float(o.buyer_reply_count_14d or 0) for o in ofds]
        meetings = [float(o.meeting_count_30d or 0) for o in ofds]
        if replies or meetings:
            reply_score = min(_safe_mean(replies) or 0.0, 5.0) / 5.0
            meeting_score = min(_safe_mean(meetings) or 0.0, 4.0) / 4.0
            row.buyer_engagement_score = round((0.6 * reply_score + 0.4 * meeting_score) * 100, 2)

        opp_count = max(1, len(ofds))
        row.objection_density_30d = round(
            obj_count_by_account.get(cid, 0) / opp_count, 3
        )

        positives = [float(o.positive_signal_count_14d or 0) for o in ofds]
        row.expansion_signal_score = round(sum(positives), 2)
        updated += 1

    await db.flush()
    return updated


# ─────────────────────── rep-level V5 augmentation ──────────────────────


async def augment_rep_features_daily(
    db: AsyncSession, *, snapshot_date: date, lookback_days: int = 90
) -> int:
    """Populate V5 columns on ``rep_features_daily`` for ``snapshot_date``.

    Lookback is rolling — we don't need history rows, just current
    state of the rep's deal book. Returns updated row count.
    """
    rows = (
        await db.execute(
            select(RepFeaturesDaily).where(
                RepFeaturesDaily.snapshot_date == snapshot_date
            )
        )
    ).scalars().all()
    if not rows:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    # All opportunities owned per rep, with outcome and discount info.
    opps_rows = (
        await db.execute(
            select(Opportunity).where(Opportunity.owner_id.isnot(None))
        )
    ).scalars().all()
    by_rep: dict[int, list[Opportunity]] = {}
    for opp in opps_rows:
        by_rep.setdefault(int(opp.owner_id), []).append(opp)

    # Objection counts per rep (resolved + total) within lookback.
    obj_rows = (
        await db.execute(
            select(Objection, Opportunity)
            .join(Opportunity, Opportunity.id == Objection.opportunity_id)
            .where(Objection.created_at >= cutoff)
        )
    ).all()
    rep_obj_total: dict[int, int] = {}
    rep_obj_resolved: dict[int, int] = {}
    for obj, opp in obj_rows:
        if opp.owner_id is None:
            continue
        rid = int(opp.owner_id)
        rep_obj_total[rid] = rep_obj_total.get(rid, 0) + 1
        if obj.resolved_flag:
            rep_obj_resolved[rid] = rep_obj_resolved.get(rid, 0) + 1

    # Discount dependence: avg latest_discount_pct from OFD for won deals.
    won_discount_rows = (
        await db.execute(
            select(OpportunityFeaturesDaily, Opportunity)
            .join(Opportunity, Opportunity.id == OpportunityFeaturesDaily.opportunity_id)
            .where(OpportunityFeaturesDaily.snapshot_date == snapshot_date)
            .where(Opportunity.stage == "closed_won")
            .where(Opportunity.owner_id.isnot(None))
        )
    ).all()
    rep_discounts: dict[int, list[float]] = {}
    for ofd, opp in won_discount_rows:
        if ofd.latest_discount_pct is None:
            continue
        rep_discounts.setdefault(int(opp.owner_id), []).append(float(ofd.latest_discount_pct))

    updated = 0
    for row in rows:
        rid = int(row.rep_id)
        rep_opps = by_rep.get(rid, [])

        total_obj = rep_obj_total.get(rid, 0)
        if total_obj > 0:
            row.objection_recovery_rate = round(
                rep_obj_resolved.get(rid, 0) / total_obj, 3
            )

        # stage_slippage_rate: deals currently in earlier stage than
        # they were 30d ago. Rule-based MVP uses ``closed_lost`` as a
        # proxy for slippage; genuine stage history lives in
        # OpportunityEvent — wire there in a follow-up.
        if rep_opps:
            lost = sum(1 for o in rep_opps if str(getattr(o, "stage", "")) == "closed_lost")
            row.stage_slippage_rate = round(lost / max(1, len(rep_opps)), 3)
            row.sample_deals = len(rep_opps)

        discounts = rep_discounts.get(rid, [])
        if discounts:
            row.discount_dependence = round(sum(discounts) / len(discounts), 3)

        # sequence_adherence_rate intentionally left None: requires
        # SequenceStepRun fan-out which V5 sprint 2 will fold in.

        updated += 1

    await db.flush()
    return updated


# ─────────────────────── orchestration helper ──────────────────────────


async def run_v5_foundation_augmentation(
    db: AsyncSession, *, snapshot_date: date
) -> V5BuildResult:
    """Run both account + rep augmentation for one snapshot date."""
    accounts = await augment_account_features_daily(db, snapshot_date=snapshot_date)
    reps = await augment_rep_features_daily(db, snapshot_date=snapshot_date)
    await db.commit()
    return V5BuildResult(
        snapshot_date=snapshot_date,
        accounts_updated=accounts,
        reps_updated=reps,
    )
