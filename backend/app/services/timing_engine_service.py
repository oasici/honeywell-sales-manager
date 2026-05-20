"""Timing Engine service (V5).

For every active opportunity, compute "what action is overdue and by
how much" relative to the segment's historical median for won deals.
The output table ``recommended_action_windows`` is what the rep-facing
UI surfaces as "Quote sent + 30h ago, segment median 18h — overdue".

Algorithm
---------
For each (segment_key, action_type) pair we compute the median gap
between the *trigger event* (e.g. ``quote_sent``) and the *target
event* (e.g. ``followup_call``) across won deals. That median is the
``ideal_gap``. Per-deal urgency is then::

    urgency = α(actual_gap − ideal_gap)
            + β(stalling_risk)
            + γ(momentum_drop)

Stalling risk and momentum drop come from the opportunity feature
store (``OpportunityFeaturesDaily``). The ``materialize_windows`` job
runs nightly and emits one ``recommended_action_windows`` row per
(opportunity, action_type) where the actual gap exceeds the ideal.

This is the rule-based MVP: median-of-historical instead of a learned
model. The interface is stable — switch in a model later by replacing
``compute_ideal_gap``.
"""

from __future__ import annotations

import json
import logging
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.opportunity import Opportunity
from app.models.sales_event_shadow import SalesEventShadow
from app.models.v5_timing import RecommendedActionWindow
from app.services.segment_key import derive_segment_key

logger = logging.getLogger(__name__)


# Triggers we currently emit windows for. Each entry maps the trigger
# event's ``event_type`` to the target action the rep should perform.
# Hours are floor values used when no historical data exists yet.
@dataclass(frozen=True)
class _TriggerSpec:
    trigger_event_type: str
    action_type: str
    fallback_ideal_hours: float
    reason_code: str


_TRIGGERS: tuple[_TriggerSpec, ...] = (
    _TriggerSpec("quote_sent", "followup_after_quote", 24.0, "post_quote_gap"),
    _TriggerSpec("meeting_logged", "meeting_summary", 12.0, "meeting_summary_gap"),
    _TriggerSpec("objection_logged", "respond_to_objection", 24.0, "objection_response_gap"),
)

# Urgency weights (α, β, γ) — see module docstring.
_W_ACTUAL_GAP = 0.6
_W_STALLING = 0.25
_W_MOMENTUM = 0.15


def _as_utc(dt: datetime) -> datetime:
    """Normalize naive datetimes to UTC.

    SQLite + the SQLAlchemy ``DateTime(timezone=True)`` column adapter
    drop tz on round-trip; Postgres preserves them. This shim keeps
    the comparison code free of branching.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ─────────────────────── ideal-gap computation ───────────────────────


async def compute_ideal_gap(
    db: AsyncSession,
    *,
    segment_key: str,
    spec: _TriggerSpec,
    lookback_days: int = 90,
) -> float:
    """Median gap (hours) between trigger and any subsequent action in
    won deals over ``lookback_days``. Falls back to ``fallback_ideal_hours``
    when there are fewer than 3 samples — too small to be statistically
    meaningful.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    # Pull trigger events + winning opps, then for each event find the
    # next non-trigger event and record the gap.
    rows = (
        await db.execute(
            select(SalesEventShadow, Opportunity)
            .join(Opportunity, Opportunity.id == SalesEventShadow.opportunity_id)
            .where(SalesEventShadow.event_type == spec.trigger_event_type)
            .where(SalesEventShadow.event_ts >= cutoff)
        )
    ).all()

    samples: list[float] = []
    for trigger_event, opp in rows:
        if str(getattr(opp, "stage", "")) != "closed_won":
            continue
        seg = derive_segment_key(
            industry=getattr(opp, "industry", None),
            employee_count=getattr(opp, "employee_count", None),
            amount_try=opp.amount,
            product_family=getattr(opp, "product_family", None),
        )
        if seg != segment_key:
            continue
        next_event = (
            await db.execute(
                select(SalesEventShadow)
                .where(SalesEventShadow.opportunity_id == opp.id)
                .where(SalesEventShadow.event_ts > trigger_event.event_ts)
                .order_by(SalesEventShadow.event_ts.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if next_event is None:
            continue
        delta = (
            _as_utc(next_event.event_ts) - _as_utc(trigger_event.event_ts)
        ).total_seconds() / 3600
        if 0 < delta < 24 * 21:  # discard >3w outliers
            samples.append(delta)

    if len(samples) < 3:
        return spec.fallback_ideal_hours
    return float(statistics.median(samples))


# ─────────────────────── per-opportunity scoring ─────────────────────


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


async def _last_trigger_event(
    db: AsyncSession, *, opportunity_id: int, event_type: str
) -> SalesEventShadow | None:
    return (
        await db.execute(
            select(SalesEventShadow)
            .where(SalesEventShadow.opportunity_id == opportunity_id)
            .where(SalesEventShadow.event_type == event_type)
            .order_by(SalesEventShadow.event_ts.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


def _urgency(actual_hours: float, ideal_hours: float, features: OpportunityFeaturesDaily | None) -> float:
    """Bounded 0..1 urgency score."""
    overdue_factor = max(0.0, (actual_hours - ideal_hours) / max(ideal_hours, 1.0))
    overdue_factor = min(overdue_factor, 3.0) / 3.0  # 0..1

    stalling = 0.0
    momentum = 0.0
    if features is not None:
        # Feature-store proxies — both 0..1 after normalization.
        if features.days_since_last_buyer_touch and features.days_since_last_buyer_touch > 0:
            stalling = min(features.days_since_last_buyer_touch, 14) / 14
        if features.momentum_score is not None:
            # momentum_score is 0..100; high momentum lowers urgency
            momentum = max(0.0, (50 - features.momentum_score) / 50)

    return round(
        _W_ACTUAL_GAP * overdue_factor
        + _W_STALLING * stalling
        + _W_MOMENTUM * momentum,
        3,
    )


# ─────────────────────── public entry points ─────────────────────────


async def materialize_windows_for_opportunity(
    db: AsyncSession, *, opportunity_id: int
) -> int:
    """Emit/refresh ``recommended_action_windows`` for one opportunity.

    Returns the number of windows written. Existing pending rows for
    the same (opp, action_type) are updated in-place; ``done`` rows
    are left alone.
    """
    opp = await db.get(Opportunity, opportunity_id)
    if opp is None or str(getattr(opp, "stage", "")) in {"closed_won", "closed_lost"}:
        return 0

    seg = derive_segment_key(
        industry=getattr(opp, "industry", None),
        employee_count=getattr(opp, "employee_count", None),
        amount_try=opp.amount,
        product_family=getattr(opp, "product_family", None),
    )
    features = await _latest_features(db, opportunity_id)
    written = 0

    for spec in _TRIGGERS:
        trigger_event = await _last_trigger_event(
            db, opportunity_id=opportunity_id, event_type=spec.trigger_event_type
        )
        if trigger_event is None:
            continue

        ideal_hours = await compute_ideal_gap(db, segment_key=seg, spec=spec)
        event_ts = _as_utc(trigger_event.event_ts)
        actual_hours = (
            datetime.now(timezone.utc) - event_ts
        ).total_seconds() / 3600
        if actual_hours <= ideal_hours:
            continue  # Not overdue; nothing to write.

        urgency = _urgency(actual_hours, ideal_hours, features)
        window_start = event_ts + timedelta(hours=ideal_hours * 0.5)
        window_end = event_ts + timedelta(hours=ideal_hours * 1.5)

        existing = (
            await db.execute(
                select(RecommendedActionWindow)
                .where(RecommendedActionWindow.opportunity_id == opportunity_id)
                .where(RecommendedActionWindow.action_type == spec.action_type)
                .where(RecommendedActionWindow.status == "pending")
                .limit(1)
            )
        ).scalar_one_or_none()

        # R6-RENDER-9 — reason_codes is typed as ``string[]`` end-to-end
        # (TS lib/types.ts:1161, OpportunityIntelligencePanel renders
        # each entry as a React child). Pre-fix this list contained one
        # string + one object, so the SPA hit React error #31 on every
        # opportunity that had a recommended action window. Flatten the
        # metadata into compact ``key=value`` strings.
        reasons: list[str] = [
            spec.reason_code,
            f"segment={seg}",
            f"ideal_hours={round(ideal_hours, 1)}",
            f"actual_hours={round(actual_hours, 1)}",
        ]
        if existing is not None:
            existing.window_start = window_start
            existing.window_end = window_end
            existing.urgency_score = urgency
            existing.reason_codes_json = json.dumps(reasons)
            existing.recommended_at = datetime.now(timezone.utc)
        else:
            db.add(
                RecommendedActionWindow(
                    opportunity_id=opportunity_id,
                    # Round-15 Sprint 15r cohort 8 — tenant_id NOT NULL.
                    # ``opp`` was loaded at the top of this function.
                    tenant_id=opp.tenant_id,
                    action_type=spec.action_type,
                    window_start=window_start,
                    window_end=window_end,
                    urgency_score=urgency,
                    reason_codes_json=json.dumps(reasons),
                )
            )
        written += 1

    await db.flush()
    return written


async def list_active_windows(
    db: AsyncSession, *, opportunity_id: int
) -> list[RecommendedActionWindow]:
    """Pending+open windows for the rep UI, ordered by urgency desc."""
    return list(
        (
            await db.execute(
                select(RecommendedActionWindow)
                .where(RecommendedActionWindow.opportunity_id == opportunity_id)
                .where(RecommendedActionWindow.status == "pending")
                .order_by(RecommendedActionWindow.urgency_score.desc().nullslast())
            )
        ).scalars()
    )


async def mark_window_done(
    db: AsyncSession, *, window_id: int
) -> RecommendedActionWindow | None:
    """Caller flips a window to ``done`` after the rep performs it."""
    win = await db.get(RecommendedActionWindow, window_id)
    if win is None:
        return None
    win.status = "done"
    win.done_at = datetime.now(timezone.utc)
    await db.flush()
    return win
