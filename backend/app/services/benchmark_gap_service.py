"""Benchmark Gap service (V5).

For each open opportunity, compute the per-metric distance from its
segment's rolling benchmark. Final score is::

    benchmark_gap = Σ wᵢ · (actualᵢ − bmᵢ) / bmᵢ

Negative gaps are *bad* (e.g. fewer stakeholders than peers).
The output is intentionally an explainable per-metric breakdown — the
UI shows "stakeholder count: 2 vs. segment median 4" rather than a
single opaque score.

Anomaly detection (z-score on segment benchmarks) lives in
``scan_anomalies`` and is wired to the nightly batch.
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.network_benchmarks import SegmentBenchmarksDaily
from app.models.opportunity import Opportunity
from app.models.v5_network import NetworkAnomaly
from app.services.segment_key import derive_segment_key

logger = logging.getLogger(__name__)


# Metrics tracked + how to extract from OpportunityFeaturesDaily, plus
# the corresponding column on SegmentBenchmarksDaily and a weight in
# the final score. Higher weight = more influence on benchmark_gap.
@dataclass(frozen=True)
class _Metric:
    name: str
    feature_attr: str
    benchmark_attr: str
    weight: float
    higher_is_better: bool


_METRICS: tuple[_Metric, ...] = (
    _Metric(
        "stakeholder_count",
        "rep_touch_count_14d",  # proxy until OFD ships explicit stakeholder count
        "avg_stakeholder_count",
        weight=0.25,
        higher_is_better=True,
    ),
    _Metric(
        "followup_speed_days",
        "days_since_last_rep_touch",
        "followup_median_days",
        weight=0.30,
        higher_is_better=False,  # lower days_since is better
    ),
    _Metric(
        "discount_pct",
        "latest_discount_pct",
        "avg_discount_pct",
        weight=0.20,
        higher_is_better=False,  # below-segment discount = healthier margin
    ),
    _Metric(
        "objection_pressure",
        "pricing_objections_30d",
        "objection_rate_14d",
        weight=0.25,
        higher_is_better=False,
    ),
)


# ─────────────────────── deal-level scoring ──────────────────────────


async def _latest_features(
    db: AsyncSession, opportunity_id: int
) -> OpportunityFeaturesDaily | None:
    return (
        await db.execute(
            select(OpportunityFeaturesDaily)
            .where(OpportunityFeaturesDaily.opportunity_id == opportunity_id)
            .order_by(OpportunityFeaturesDaily.snapshot_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _latest_benchmark(
    db: AsyncSession, segment_key: str
) -> SegmentBenchmarksDaily | None:
    return (
        await db.execute(
            select(SegmentBenchmarksDaily)
            .where(SegmentBenchmarksDaily.segment_key == segment_key)
            .order_by(SegmentBenchmarksDaily.snapshot_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _signed_pct_diff(actual: float, benchmark: float, higher_is_better: bool) -> float:
    """Return signed normalized difference. Negative means worse than peers."""
    if benchmark <= 0:
        return 0.0
    raw = (actual - benchmark) / benchmark
    return raw if higher_is_better else -raw


async def score_opportunity(db: AsyncSession, opportunity_id: int) -> dict:
    """Standard explainability envelope for one opportunity.

    Returns the full ``{value, confidence, drivers, benchmark_context,
    recommended_actions}`` shape used by other V5 services. ``value``
    here is the weighted ``benchmark_gap``: 0 = matches segment, < 0
    = lagging, > 0 = ahead.
    """
    opp = await db.get(Opportunity, opportunity_id)
    if opp is None:
        return {
            "value": None,
            "confidence": 0.0,
            "drivers": [],
            "benchmark_context": {},
            "recommended_actions": ["opportunity_not_found"],
        }

    seg = derive_segment_key(
        industry=getattr(opp, "industry", None),
        employee_count=getattr(opp, "employee_count", None),
        amount_try=opp.amount,
        product_family=getattr(opp, "product_family", None),
    )
    features = await _latest_features(db, opportunity_id)
    benchmark = await _latest_benchmark(db, seg)

    if features is None or benchmark is None:
        return {
            "value": None,
            "confidence": 0.0,
            "drivers": [],
            "benchmark_context": {"segment_key": seg, "sample_size": 0},
            "recommended_actions": [],
        }

    drivers: list[dict] = []
    weighted_sum = 0.0
    weight_total = 0.0
    benchmark_ctx: dict = {"segment_key": seg, "sample_size": benchmark.sample_size}

    for metric in _METRICS:
        actual = getattr(features, metric.feature_attr, None)
        bm = getattr(benchmark, metric.benchmark_attr, None)
        if actual is None or bm is None:
            continue
        diff = _signed_pct_diff(float(actual), float(bm), metric.higher_is_better)
        weighted_sum += diff * metric.weight
        weight_total += metric.weight
        drivers.append(
            {
                "label": metric.name,
                "actual": round(float(actual), 2),
                "benchmark": round(float(bm), 2),
                "impact": round(diff * metric.weight, 3),
            }
        )
        benchmark_ctx[f"{metric.name}_actual"] = round(float(actual), 2)
        benchmark_ctx[f"{metric.name}_benchmark"] = round(float(bm), 2)

    final_score = round(weighted_sum / weight_total, 3) if weight_total else 0.0
    # confidence scales with sample_size; we cap at 1.0 once we've seen
    # 30+ deals in the segment.
    confidence = min(1.0, benchmark.sample_size / 30.0) if benchmark.sample_size else 0.0

    recommended: list[str] = []
    laggards = [d for d in drivers if d["impact"] < -0.05]
    laggards.sort(key=lambda d: d["impact"])  # most negative first
    for d in laggards[:3]:
        recommended.append(f"close_gap:{d['label']}")

    return {
        "value": final_score,
        "confidence": round(confidence, 2),
        "drivers": drivers,
        "benchmark_context": benchmark_ctx,
        "recommended_actions": recommended,
    }


# ─────────────────────── network anomaly detection ───────────────────


async def scan_anomalies(
    db: AsyncSession, *, lookback_days: int = 28, z_threshold: float = 2.0
) -> int:
    """Run a z-score scan over each segment's benchmark history.

    Writes one ``network_anomalies`` row per metric where the latest
    value exceeds ``±z_threshold`` standard deviations from the
    rolling mean. Returns the number of anomalies persisted.
    """
    cutoff_date = date.today() - timedelta(days=lookback_days)

    # Load all segments seen recently. We cap at ``lookback_days`` rows
    # so a seg with 1000 days of history still loads in one pass.
    all_rows = (
        await db.execute(
            select(SegmentBenchmarksDaily)
            .where(SegmentBenchmarksDaily.snapshot_date >= cutoff_date)
            .order_by(
                SegmentBenchmarksDaily.segment_key,
                SegmentBenchmarksDaily.snapshot_date,
            )
        )
    ).scalars().all()

    by_segment: dict[str, list[SegmentBenchmarksDaily]] = {}
    for row in all_rows:
        by_segment.setdefault(row.segment_key, []).append(row)

    anomalies_written = 0
    metric_columns = (
        "win_rate_90d",
        "followup_median_days",
        "avg_discount_pct",
        "avg_stakeholder_count",
        "objection_rate_14d",
    )

    for segment_key, rows in by_segment.items():
        if len(rows) < 7:
            continue  # too thin for variance estimate
        latest = rows[-1]
        history = rows[:-1]

        for col in metric_columns:
            values = [getattr(r, col) for r in history if getattr(r, col) is not None]
            if len(values) < 5:
                continue
            actual = getattr(latest, col)
            if actual is None:
                continue
            try:
                mean = statistics.fmean(values)
                stdev = statistics.pstdev(values)
            except statistics.StatisticsError:
                continue
            if stdev == 0:
                continue
            z = (float(actual) - mean) / stdev
            if abs(z) < z_threshold:
                continue
            severity = "high" if abs(z) >= 3 else "med"
            db.add(
                NetworkAnomaly(
                    segment_key=segment_key,
                    metric_name=col,
                    expected_value=round(mean, 4),
                    actual_value=round(float(actual), 4),
                    z_score=round(z, 3),
                    severity=severity,
                    explanation_json=json.dumps(
                        {
                            "lookback_days": lookback_days,
                            "history_n": len(values),
                            "stdev": round(stdev, 4),
                        }
                    ),
                    detected_at=datetime.now(timezone.utc),
                )
            )
            anomalies_written += 1

    await db.flush()
    return anomalies_written
