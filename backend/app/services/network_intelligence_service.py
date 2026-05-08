"""Network Intelligence façade.

Plan adoption — Phase 5 / Sprint 21-22 unified read API.
Composes ``benchmark_gap_service``, ``federated_benchmark_service``, and
``NetworkSegment``/``SegmentBenchmarksDaily`` into a single manager-facing
read surface — the manager-insight cards the plan describes.

This is intentionally a thin orchestration layer. Mutation/materialization
logic stays in the underlying services and the nightly batch.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.network_benchmarks import NetworkSegment, SegmentBenchmarksDaily
from app.models.opportunity import Opportunity
from app.models.user import User
from app.models.v6_federated import FederatedBenchmark
from app.services.benchmark_gap_service import _METRICS as METRIC_DEFS  # noqa: F401
from app.services.tenant_context import scoped_for_user


_KEY_METRICS = (
    ("followup_median_days", "Follow-up speed (days)", False),
    ("avg_stakeholder_count", "Stakeholder coverage", True),
    ("avg_discount_pct", "Discount level (%)", False),
    ("objection_rate_14d", "Objection rate (14d)", False),
    ("win_rate_90d", "Win rate (90d)", True),
)


async def get_segment_overview(
    db: AsyncSession,
    current_user: User,
    segment_key: str | None = None,
) -> dict[str, Any]:
    """Top-line "how do we compare to segment" view.

    Returns the latest segment benchmarks the caller's tenant can see plus
    the per-metric gap (caller's tenant median vs. segment median).
    """
    # Pick segment: caller-provided, else the most populous in this tenant
    if segment_key is None:
        seg = (
            await db.execute(
                select(NetworkSegment)
                .where(
                    (NetworkSegment.tenant_id == current_user.tenant_id)
                    | (NetworkSegment.tenant_id.is_(None))
                )
                .order_by(NetworkSegment.id.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        segment_key = seg.segment_key if seg else "stage:qualified"

    bench = (
        await db.execute(
            select(SegmentBenchmarksDaily)
            .where(SegmentBenchmarksDaily.segment_key == segment_key)
            .order_by(desc(SegmentBenchmarksDaily.snapshot_date))
            .limit(1)
        )
    ).scalar_one_or_none()

    if bench is None:
        return {
            "segment_key": segment_key,
            "snapshot_date": None,
            "metrics": [],
            "tenant_metrics": {},
        }

    # Tenant rollup from feature store daily
    cutoff = date.today() - timedelta(days=30)
    rows_q = scoped_for_user(
        select(OpportunityFeaturesDaily)
        .join(Opportunity, Opportunity.id == OpportunityFeaturesDaily.opportunity_id)
        .where(OpportunityFeaturesDaily.snapshot_date >= cutoff),
        current_user,
        column=Opportunity.tenant_id,
    )
    rows = (await db.execute(rows_q)).scalars().all()

    tenant_followup = _median([r.days_since_last_rep_touch for r in rows if r.days_since_last_rep_touch is not None])
    tenant_stakeholders = _avg([r.decision_maker_count for r in rows if r.decision_maker_count is not None])
    tenant_discount = _avg([r.latest_discount_pct for r in rows if r.latest_discount_pct is not None])
    tenant_objections = _rate(
        [r.pricing_objections_30d for r in rows], window_days=30
    )

    tenant_metrics = {
        "followup_median_days": tenant_followup,
        "avg_stakeholder_count": tenant_stakeholders,
        "avg_discount_pct": tenant_discount,
        "objection_rate_14d": tenant_objections,
        "win_rate_90d": None,
    }

    metrics_out: list[dict[str, Any]] = []
    for key, label, higher_is_better in _KEY_METRICS:
        bench_value = getattr(bench, key, None)
        actual = tenant_metrics.get(key)
        gap_pct = _gap_pct(actual, bench_value, higher_is_better)
        metrics_out.append(
            {
                "key": key,
                "label": label,
                "tenant_value": _round(actual),
                "segment_value": _round(bench_value),
                "higher_is_better": higher_is_better,
                "gap_pct": gap_pct,
                "verdict": _verdict(gap_pct),
            }
        )

    return {
        "segment_key": segment_key,
        "snapshot_date": bench.snapshot_date.isoformat() if bench.snapshot_date else None,
        "sample_size": bench.sample_size,
        "metrics": metrics_out,
    }


async def list_segments(db: AsyncSession, current_user: User) -> list[dict[str, Any]]:
    """All segments the caller can see."""
    rows = (
        await db.execute(
            select(NetworkSegment)
            .where(
                (NetworkSegment.tenant_id == current_user.tenant_id)
                | (NetworkSegment.tenant_id.is_(None))
            )
            .order_by(NetworkSegment.name.asc())
        )
    ).scalars().all()
    return [
        {"segment_key": r.segment_key, "name": r.name, "tenant_id": r.tenant_id}
        for r in rows
    ]


async def list_federated(
    db: AsyncSession,
    current_user: User,
    benchmark_key: str,
    include_suppressed: bool = False,
) -> list[dict[str, Any]]:
    """Federated cross-tenant benchmark series for a given key.

    Round-8 R8-TEN-2 — only the caller's own tenant rows + globally-shared
    rows (``tenant_id IS NULL``) are returned. Cross-tenant rows are
    filtered out at the query layer.
    """
    stmt = (
        select(FederatedBenchmark)
        .where(FederatedBenchmark.benchmark_key == benchmark_key)
        .where(
            (FederatedBenchmark.tenant_id == current_user.tenant_id)
            | (FederatedBenchmark.tenant_id.is_(None))
        )
        .order_by(desc(FederatedBenchmark.snapshot_date))
        .limit(60)
    )
    if not include_suppressed:
        stmt = stmt.where(FederatedBenchmark.suppressed.is_(False))
    rows = (await db.execute(stmt)).scalars().all()
    return [
        {
            "benchmark_key": r.benchmark_key,
            "snapshot_date": r.snapshot_date.isoformat() if r.snapshot_date else None,
            "metric_name": r.metric_name,
            "metric_value": r.metric_value,
            "sample_size": r.sample_size,
            "tenant_count": r.tenant_count,
            "suppressed": bool(r.suppressed),
        }
        for r in rows
    ]


# ── Helpers ──

def _median(values: list[float]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    if n % 2 == 1:
        return float(s[n // 2])
    return (float(s[n // 2 - 1]) + float(s[n // 2])) / 2.0


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(float(v) for v in values) / len(values)


def _rate(counts: list[int], window_days: int) -> float | None:
    if not counts:
        return None
    return sum(int(c or 0) for c in counts) / max(1, len(counts))


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def _gap_pct(tenant: float | None, segment: float | None, higher_is_better: bool) -> float | None:
    if tenant is None or segment is None or segment == 0:
        return None
    raw = (tenant - segment) / segment * 100.0
    if not higher_is_better:
        raw = -raw
    return round(raw, 1)


def _verdict(gap_pct: float | None) -> str:
    if gap_pct is None:
        return "unknown"
    if gap_pct >= 10:
        return "leading"
    if gap_pct >= -10:
        return "on_par"
    if gap_pct >= -25:
        return "lagging"
    return "critical"
