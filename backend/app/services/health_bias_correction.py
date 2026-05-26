"""D-033 — Customer Health zero-data bias correction.

Pre-Round-19 a new customer with no signals (no invoices, no calls,
no breaches) scored 0 on every component → was auto-flagged at-risk.
False positive: a 2-day-old customer has no signal, not a bad
relationship.

This module returns a "confidence-weighted" score so the Cockpit
At-Risk view can hide low-confidence rows.

Contract:

  ``correct_for_data_sparsity(raw_score, signal_count)`` returns
  ``(adjusted_score, confidence)`` where:

    * ``signal_count`` is the number of components that had real
      data (e.g. ≥1 invoice, ≥1 activity, etc.). Max 6.
    * confidence = signal_count / 6 (range 0.0 – 1.0).
    * When confidence < 0.3, adjusted_score = 50 (neutral).
    * Otherwise the raw score passes through unchanged.

The Cockpit At-Risk card filters to ``confidence >= 0.3`` so new
customers no longer dominate the badge count.
"""

from __future__ import annotations

from dataclasses import dataclass

_NEUTRAL_SCORE = 50
_MIN_CONFIDENCE_FOR_RAW = 0.3


@dataclass(frozen=True)
class HealthScore:
    """Result of the corrected health computation."""

    value: int                  # 0..100
    confidence: float           # 0.0..1.0
    raw_value: int              # the uncorrected raw computation
    signal_count: int           # how many components had real data


def correct_for_data_sparsity(
    raw_score: int,
    signal_count: int,
    *,
    max_signals: int = 6,
) -> HealthScore:
    """Pure function. Returns the corrected score + confidence band.

    Examples:
      * Established customer: signal_count=6, raw=42  → value=42, conf=1.0
      * New customer:         signal_count=0, raw=0   → value=50, conf=0.0
      * Sparse customer:      signal_count=1, raw=15  → value=50, conf=0.17
    """
    confidence = max(0.0, min(1.0, signal_count / max(max_signals, 1)))
    if confidence < _MIN_CONFIDENCE_FOR_RAW:
        return HealthScore(
            value=_NEUTRAL_SCORE,
            confidence=confidence,
            raw_value=raw_score,
            signal_count=signal_count,
        )
    return HealthScore(
        value=int(round(raw_score)),
        confidence=confidence,
        raw_value=int(round(raw_score)),
        signal_count=signal_count,
    )


def is_displayable_in_at_risk(score: HealthScore, threshold: int) -> bool:
    """Cockpit At-Risk filter: hide low-confidence rows from the badge."""
    return score.confidence >= _MIN_CONFIDENCE_FOR_RAW and score.value < threshold
