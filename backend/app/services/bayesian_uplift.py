"""Bayesian uplift helpers (V7).

Closed-form Beta-prior smoothing for binary win-rate metrics. We
deliberately avoid pulling in scipy here — the closed-form mean +
variance + normal-approx CI is enough for our scale (small numbers
of patterns per segment, no need for full posterior sampling).

Formulas
--------
Prior: ``Beta(α₀, β₀)`` with α₀ = baseline · prior_strength,
β₀ = (1 − baseline) · prior_strength.

Posterior: ``Beta(α₀ + wins, β₀ + losses)``.

- ``smoothed_winrate`` = posterior mean = (α₀ + wins) / (α₀ + β₀ + n)
- ``uplift_score``     = smoothed_winrate − baseline (additive lift)
- ``ci_low/ci_high``   = ±1.96·√(var) bounds (normal approximation,
  good enough for n ≥ 5; for tiny samples the prior dominates anyway)
"""

from __future__ import annotations

import math
from dataclasses import dataclass


DEFAULT_PRIOR_STRENGTH = 10.0
_Z_95 = 1.96


@dataclass(frozen=True)
class UpliftStats:
    smoothed_winrate: float
    uplift_score: float
    ci_low: float
    ci_high: float
    is_promotable: bool


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_uplift(
    *,
    wins: int,
    support: int,
    baseline_winrate: float,
    prior_strength: float = DEFAULT_PRIOR_STRENGTH,
) -> UpliftStats:
    """Bayesian-smoothed uplift stats for one (pattern, segment) cell.

    ``is_promotable`` is True iff the 95% CI lower bound for the
    smoothed winrate is *above* the baseline — i.e. we have enough
    signal to be confident the pattern beats the segment average.
    """
    baseline = _clip01(baseline_winrate)
    if support < 0 or wins < 0 or wins > support:
        return UpliftStats(
            smoothed_winrate=baseline,
            uplift_score=0.0,
            ci_low=baseline,
            ci_high=baseline,
            is_promotable=False,
        )

    alpha0 = max(0.0, baseline * prior_strength)
    beta0 = max(0.0, (1 - baseline) * prior_strength)

    alpha = alpha0 + wins
    beta = beta0 + (support - wins)
    n_total = alpha + beta

    smoothed = alpha / n_total if n_total > 0 else baseline
    # Beta(α, β) variance = αβ / ((α+β)² (α+β+1))
    variance = (alpha * beta) / ((n_total ** 2) * (n_total + 1)) if n_total > 0 else 0.0
    stddev = math.sqrt(variance)
    ci_low = _clip01(smoothed - _Z_95 * stddev)
    ci_high = _clip01(smoothed + _Z_95 * stddev)

    is_promotable = (
        support >= 5  # bare minimum sample so the CI isn't dominated by prior
        and ci_low > baseline
        and smoothed > baseline
    )

    return UpliftStats(
        smoothed_winrate=round(smoothed, 4),
        uplift_score=round(smoothed - baseline, 4),
        ci_low=round(ci_low, 4),
        ci_high=round(ci_high, 4),
        is_promotable=is_promotable,
    )
