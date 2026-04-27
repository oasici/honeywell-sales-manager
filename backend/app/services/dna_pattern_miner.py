"""DNA pattern miner (V5) — segment-level behavioural pattern discovery.

The "DNA" of a winning deal in segment ``S`` is the canonical sequence
of high-signal events (e.g. ``meeting → quote → followup``) that
historically maps to closed-won outcomes. This miner reads the
``v4_sales_events_shadow`` table and writes ``dna_patterns`` rows
plus a small set of human-facing ``dna_recommendations``.

Approach (rule-based MVP)
-------------------------
1. For each (segment_key, won_opp), pull the ordered event sequence
   and reduce it to a *signature* of high-signal types only.
2. Count signature support per segment.
3. Compare per-segment win rate (within sequence) against baseline
   (segment overall win rate). A signature is a "pattern" when it has
   ≥3 supporting deals AND lift ≥ 1.2.
4. The top-K patterns become recommendations: {recommended sequence,
   lift, sample size}.

This is intentionally simple — pluggable so we can swap in PrefixSpan
or a learned sequence model later without changing the consumers.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import func

from app.models.opportunity import Opportunity
from app.models.sales_event_shadow import SalesEventShadow
from app.models.sequence_v2 import Stakeholder
from app.models.feature_store_daily import OpportunityFeaturesDaily
from app.models.v5_dna_patterns import DnaPattern, DnaRecommendation
from app.services.segment_key import derive_segment_key
from app.services.sequence_tokenizer import TokenizerContext, tokenize

logger = logging.getLogger(__name__)


# Event types we treat as "high signal" — anything else is dropped
# from the raw filter so the tokenizer only sees relevant inputs.
_SIGNAL_EVENTS: frozenset[str] = frozenset(
    {
        "email_sent",
        "email_received",
        "call_logged",
        "meeting_booked",
        "meeting_logged",
        "quote_sent",
        "objection_logged",
        "stakeholder_added",
        "demo_completed",
        "proposal_sent",
        "contract_sent",
        "stage_changed",
    }
)

_MIN_SUPPORT = 3
_MIN_LIFT = 1.2
_MAX_PATTERNS_PER_SEGMENT = 5


def _signature(events: list[SalesEventShadow]) -> tuple[str, ...]:
    """Reduce an ordered event list to a tuple of high-signal types.

    Kept for backward compat with the V5 unit tests; the new path
    used by ``mine_patterns`` is :func:`_tokenize_for_opp` which calls
    the V6 high-level tokenizer.
    """
    return tuple(e.event_type for e in events if e.event_type in _SIGNAL_EVENTS)


async def _tokenize_for_opp(
    db, *, opportunity: Opportunity, events: list[SalesEventShadow]
) -> tuple[str, ...]:
    """Run the V6 sequence tokenizer with per-opp context loaded from DB."""
    sh_count = (
        await db.execute(
            select(func.count(Stakeholder.id)).where(
                Stakeholder.opportunity_id == opportunity.id
            )
        )
    ).scalar() or 0

    ofd = (
        await db.execute(
            select(OpportunityFeaturesDaily)
            .where(OpportunityFeaturesDaily.opportunity_id == opportunity.id)
            .order_by(OpportunityFeaturesDaily.snapshot_date.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    ctx = TokenizerContext(
        stakeholder_count=int(sh_count),
        decision_maker_count=int(ofd.decision_maker_count) if ofd else 0,
        latest_discount_pct=float(ofd.latest_discount_pct) if ofd and ofd.latest_discount_pct else None,
    )
    # Pre-filter to high-signal events so the tokenizer scans less.
    filtered = [e for e in events if e.event_type in _SIGNAL_EVENTS]
    return tuple(tokenize(filtered, ctx))


async def _opportunity_events(
    db: AsyncSession, *, opportunity_id: int, since: datetime
) -> list[SalesEventShadow]:
    return list(
        (
            await db.execute(
                select(SalesEventShadow)
                .where(SalesEventShadow.opportunity_id == opportunity_id)
                .where(SalesEventShadow.event_ts >= since)
                .order_by(SalesEventShadow.event_ts.asc())
            )
        ).scalars()
    )


async def mine_patterns(
    db: AsyncSession, *, lookback_days: int = 180
) -> int:
    """Recompute DNA patterns from the last ``lookback_days`` of data.

    Returns the count of pattern rows written/updated.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    opps = (
        await db.execute(
            select(Opportunity).where(Opportunity.created_at >= cutoff)
        )
    ).scalars().all()
    if not opps:
        return 0

    # Bucket per segment, separately tracking won vs total for baseline.
    seg_signatures: dict[str, Counter] = {}
    seg_won: dict[str, int] = {}
    seg_total: dict[str, int] = {}
    seg_won_signatures: dict[str, Counter] = {}

    for opp in opps:
        seg = derive_segment_key(
            industry=getattr(opp, "industry", None),
            employee_count=getattr(opp, "employee_count", None),
            amount_try=opp.amount,
            product_family=getattr(opp, "product_family", None),
        )
        seg_total[seg] = seg_total.get(seg, 0) + 1
        events = await _opportunity_events(db, opportunity_id=int(opp.id), since=cutoff)
        sig = await _tokenize_for_opp(db, opportunity=opp, events=events)
        if not sig:
            continue
        seg_signatures.setdefault(seg, Counter())[sig] += 1
        if str(getattr(opp, "stage", "")) == "closed_won":
            seg_won[seg] = seg_won.get(seg, 0) + 1
            seg_won_signatures.setdefault(seg, Counter())[sig] += 1

    written = 0
    for seg, total in seg_total.items():
        baseline = (seg_won.get(seg, 0) / total) if total else 0.0
        if baseline <= 0:
            continue
        won_sigs = seg_won_signatures.get(seg, Counter())
        all_sigs = seg_signatures.get(seg, Counter())
        candidates = []
        for sig, won_count in won_sigs.most_common():
            support = all_sigs.get(sig, 0)
            if support < _MIN_SUPPORT:
                continue
            local_win_rate = won_count / support
            lift = local_win_rate / baseline if baseline else 0.0
            if lift < _MIN_LIFT:
                continue
            candidates.append((sig, support, local_win_rate, lift))

        for sig, support, win_rate, lift in candidates[:_MAX_PATTERNS_PER_SEGMENT]:
            pattern_name = " → ".join(sig)
            existing = (
                await db.execute(
                    select(DnaPattern)
                    .where(DnaPattern.segment_key == seg)
                    .where(DnaPattern.pattern_name == pattern_name)
                )
            ).scalar_one_or_none()
            if existing is None:
                pattern = DnaPattern(
                    segment_key=seg,
                    pattern_name=pattern_name,
                    pattern_type="event_sequence",
                    sequence_template_json=json.dumps(list(sig)),
                    support_count=support,
                    win_rate=round(win_rate, 3),
                    baseline_win_rate=round(baseline, 3),
                    lift_vs_baseline=round(lift, 3),
                    confidence_score=round(min(1.0, support / 20.0), 3),
                )
                db.add(pattern)
                await db.flush()
                source_id = pattern.id
            else:
                existing.sequence_template_json = json.dumps(list(sig))
                existing.support_count = support
                existing.win_rate = round(win_rate, 3)
                existing.baseline_win_rate = round(baseline, 3)
                existing.lift_vs_baseline = round(lift, 3)
                existing.confidence_score = round(min(1.0, support / 20.0), 3)
                existing.last_trained_at = datetime.now(timezone.utc)
                source_id = existing.id

            db.add(
                DnaRecommendation(
                    segment_key=seg,
                    stage_scope=None,
                    recommendation_json=json.dumps(
                        {
                            "sequence": list(sig),
                            "win_rate": round(win_rate, 3),
                            "baseline": round(baseline, 3),
                            "lift": round(lift, 3),
                            "support": support,
                        }
                    ),
                    source_pattern_id=source_id,
                )
            )
            written += 1

    await db.flush()
    return written


async def list_recommendations_for_segment(
    db: AsyncSession, *, segment_key: str, limit: int = 10
) -> list[dict]:
    """Most recent recommendations for the rep-facing UI."""
    rows = (
        await db.execute(
            select(DnaRecommendation)
            .where(DnaRecommendation.segment_key == segment_key)
            .order_by(DnaRecommendation.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    out: list[dict] = []
    for r in rows:
        try:
            payload = json.loads(r.recommendation_json)
        except (json.JSONDecodeError, TypeError):
            continue
        out.append(
            {
                "id": r.id,
                "segment_key": r.segment_key,
                "stage_scope": r.stage_scope,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                **payload,
            }
        )
    return out
