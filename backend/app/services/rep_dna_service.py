"""Rep DNA profiling service (V5).

Builds a per-rep behavioural profile from ``rep_features_daily`` so we
can answer "what kind of seller is this rep?" — e.g. fast follow-up
specialist, discount-heavy closer, network-builder. Output lives in
``rep_dna_profiles`` (one row per rep) and feeds the coaching UI.

This is the rule-based MVP: we threshold the rep's metrics against
team-level means and assign a primary cluster label + structured
strengths/gaps. Pluggable — swap thresholds for a learned classifier
later by replacing ``classify_rep`` without touching consumers.
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_store_daily import RepFeaturesDaily
from app.models.v5_similarity import RepDnaProfile

logger = logging.getLogger(__name__)


# Cluster labels we surface today. Keep small + intentional — UI maps
# each label to a coaching template.
CLUSTER_FAST_FOLLOWUP = "fast_followup"
CLUSTER_DISCOUNT_HEAVY = "discount_heavy"
CLUSTER_NETWORK_BUILDER = "network_builder"
CLUSTER_OBJECTION_HANDLER = "objection_handler"
CLUSTER_BALANCED = "balanced"


@dataclass
class _TeamStats:
    avg_followup_hours: float | None
    discount_dependence: float | None
    objection_recovery_rate: float | None
    stakeholder_coverage_rate: float | None


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


async def _team_stats(db: AsyncSession, *, snapshot_date: date) -> _TeamStats:
    rows = (
        await db.execute(
            select(RepFeaturesDaily).where(
                RepFeaturesDaily.snapshot_date == snapshot_date
            )
        )
    ).scalars().all()
    if not rows:
        return _TeamStats(None, None, None, None)
    return _TeamStats(
        avg_followup_hours=_mean(
            [float(r.avg_followup_hours) for r in rows if r.avg_followup_hours is not None]
        ),
        discount_dependence=_mean(
            [float(r.discount_dependence) for r in rows if r.discount_dependence is not None]
        ),
        objection_recovery_rate=_mean(
            [
                float(r.objection_recovery_rate)
                for r in rows
                if r.objection_recovery_rate is not None
            ]
        ),
        stakeholder_coverage_rate=_mean(
            [
                float(r.stakeholder_coverage_rate)
                for r in rows
                if r.stakeholder_coverage_rate is not None
            ]
        ),
    )


def classify_rep(
    *, rep: RepFeaturesDaily, team: _TeamStats
) -> tuple[str, list[str], list[str]]:
    """Return (cluster_label, strengths, gaps) for one rep snapshot.

    Threshold rule of thumb: a metric is a "strength" when ≥1.2× team
    median (or, for "lower is better" metrics, ≤0.8×). Gaps are the
    inverse. The dominant strength picks the cluster label; falls back
    to ``balanced`` when no metric stands out.
    """
    strengths: list[str] = []
    gaps: list[str] = []

    if team.avg_followup_hours is not None and rep.avg_followup_hours is not None:
        if rep.avg_followup_hours <= team.avg_followup_hours * 0.8:
            strengths.append("fast_followup")
        elif rep.avg_followup_hours >= team.avg_followup_hours * 1.2:
            gaps.append("slow_followup")

    if team.discount_dependence is not None and rep.discount_dependence is not None:
        if rep.discount_dependence >= team.discount_dependence * 1.2:
            gaps.append("discount_heavy")
        elif rep.discount_dependence <= team.discount_dependence * 0.8:
            strengths.append("margin_discipline")

    if (
        team.objection_recovery_rate is not None
        and rep.objection_recovery_rate is not None
    ):
        if rep.objection_recovery_rate >= team.objection_recovery_rate * 1.2:
            strengths.append("objection_handler")
        elif rep.objection_recovery_rate <= team.objection_recovery_rate * 0.8:
            gaps.append("objection_resolution_low")

    if (
        team.stakeholder_coverage_rate is not None
        and rep.stakeholder_coverage_rate is not None
    ):
        if rep.stakeholder_coverage_rate >= team.stakeholder_coverage_rate * 1.2:
            strengths.append("network_builder")
        elif rep.stakeholder_coverage_rate <= team.stakeholder_coverage_rate * 0.8:
            gaps.append("thin_buyer_network")

    # Pick the primary cluster from the strongest strength tag.
    cluster_priority = (
        ("fast_followup", CLUSTER_FAST_FOLLOWUP),
        ("network_builder", CLUSTER_NETWORK_BUILDER),
        ("objection_handler", CLUSTER_OBJECTION_HANDLER),
    )
    cluster = CLUSTER_BALANCED
    for tag, label in cluster_priority:
        if tag in strengths:
            cluster = label
            break
    if cluster == CLUSTER_BALANCED and "discount_heavy" in gaps:
        cluster = CLUSTER_DISCOUNT_HEAVY

    return cluster, strengths, gaps


async def build_rep_dna_profile(
    db: AsyncSession, *, rep_id: int, snapshot_date: date
) -> RepDnaProfile | None:
    """Recompute one rep's DNA profile against team stats for ``snapshot_date``.

    Returns the upserted row, or ``None`` if the rep has no features
    snapshot (nothing to base the profile on).
    """
    rep_row = (
        await db.execute(
            select(RepFeaturesDaily)
            .where(RepFeaturesDaily.rep_id == rep_id)
            .where(RepFeaturesDaily.snapshot_date == snapshot_date)
        )
    ).scalar_one_or_none()
    if rep_row is None:
        return None

    team = await _team_stats(db, snapshot_date=snapshot_date)
    cluster, strengths, gaps = classify_rep(rep=rep_row, team=team)

    profile_payload = {
        "snapshot_date": snapshot_date.isoformat(),
        "metrics": {
            "avg_followup_hours": rep_row.avg_followup_hours,
            "discount_dependence": rep_row.discount_dependence,
            "objection_recovery_rate": rep_row.objection_recovery_rate,
            "stakeholder_coverage_rate": rep_row.stakeholder_coverage_rate,
            "stage_slippage_rate": rep_row.stage_slippage_rate,
            "sample_deals": rep_row.sample_deals,
        },
        "team_baseline": {
            "avg_followup_hours": team.avg_followup_hours,
            "discount_dependence": team.discount_dependence,
            "objection_recovery_rate": team.objection_recovery_rate,
            "stakeholder_coverage_rate": team.stakeholder_coverage_rate,
        },
    }

    period_end = snapshot_date
    period_start = snapshot_date - timedelta(days=90)

    existing = await db.get(RepDnaProfile, rep_id)
    if existing is None:
        existing = RepDnaProfile(
            rep_id=rep_id,
            cluster_label=cluster,
            profile_json=json.dumps(profile_payload),
            strengths_json=json.dumps(strengths),
            gaps_json=json.dumps(gaps),
            sample_period_start=period_start,
            sample_period_end=period_end,
        )
        db.add(existing)
    else:
        existing.cluster_label = cluster
        existing.profile_json = json.dumps(profile_payload)
        existing.strengths_json = json.dumps(strengths)
        existing.gaps_json = json.dumps(gaps)
        existing.sample_period_start = period_start
        existing.sample_period_end = period_end
        existing.generated_at = datetime.now(timezone.utc)

    await db.flush()
    return existing


async def refresh_all_rep_dna(db: AsyncSession, *, snapshot_date: date) -> int:
    """Run ``build_rep_dna_profile`` for every rep with a snapshot row."""
    rep_ids = (
        await db.execute(
            select(RepFeaturesDaily.rep_id).where(
                RepFeaturesDaily.snapshot_date == snapshot_date
            )
        )
    ).scalars().all()
    written = 0
    for rid in {int(r) for r in rep_ids}:
        if await build_rep_dna_profile(db, rep_id=rid, snapshot_date=snapshot_date):
            written += 1
    return written
