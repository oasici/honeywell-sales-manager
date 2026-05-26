"""Round-19 Phase 6 — finishing-batch tests.

F-012 multi-currency forecast rollup + F-014 health-recompute debouncer.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest


# ────────────────────────────────────────────────────────────────────
# F-012 — Multi-currency forecast rollup (pure)
# ────────────────────────────────────────────────────────────────────


from app.services.multi_currency_forecast import (
    CurrencyBucket,
    ForecastRollup,
    OppView,
    compute_rollup,
)


def _opp(
    *,
    amount,
    currency,
    probability,
    stage="prospecting",
    fx=None,
) -> OppView:
    return OppView(
        opp_id=1,
        amount=Decimal(str(amount)),
        currency=currency,
        probability=Decimal(str(probability)),
        stage=stage,
        fx_rate_to_base=(Decimal(str(fx)) if fx is not None else None),
    )


def test_rollup_groups_by_currency() -> None:
    rollup = compute_rollup(
        [
            _opp(amount=100_000, currency="TRY", probability=0.5),
            _opp(amount=50_000, currency="USD", probability=0.5),
            _opp(amount=30_000, currency="EUR", probability=0.5),
        ],
        base_currency="TRY",
    )
    assert set(rollup.by_currency.keys()) == {"TRY", "USD", "EUR"}


def test_rollup_weighted_amount_equals_amount_times_probability() -> None:
    rollup = compute_rollup(
        [_opp(amount=10_000, currency="TRY", probability=0.5)],
        base_currency="TRY",
    )
    bucket = rollup.by_currency["TRY"]
    assert bucket.weighted_amount == Decimal("5000")
    assert bucket.open_amount == Decimal("10000")
    assert bucket.open_count == 1


def test_commit_threshold_is_sticky_at_75_pct() -> None:
    """0.74 → not commit; 0.75 → commit; 0.99 → commit."""
    r = compute_rollup(
        [
            _opp(amount=1000, currency="TRY", probability=0.74),
            _opp(amount=2000, currency="TRY", probability=0.75),
            _opp(amount=3000, currency="TRY", probability=0.99),
        ],
        base_currency="TRY",
    )
    assert r.by_currency["TRY"].commit_amount == Decimal("5000")


def test_closed_lost_excluded_from_open() -> None:
    r = compute_rollup(
        [
            _opp(amount=10_000, currency="TRY", probability=0.5, stage="closed_lost"),
            _opp(amount=5_000, currency="TRY", probability=0.5),
        ],
        base_currency="TRY",
    )
    bucket = r.by_currency["TRY"]
    assert bucket.open_amount == Decimal("5000")
    assert bucket.closed_lost_amount == Decimal("10000")


def test_closed_won_separated_from_open() -> None:
    r = compute_rollup(
        [
            _opp(amount=10_000, currency="TRY", probability=1.0, stage="closed_won"),
            _opp(amount=5_000, currency="TRY", probability=0.5),
        ],
        base_currency="TRY",
    )
    bucket = r.by_currency["TRY"]
    assert bucket.open_amount == Decimal("5000")
    assert bucket.closed_won_amount == Decimal("10000")
    assert r.base_total_closed_won == Decimal("10000")


def test_base_currency_conversion_uses_fx_snapshot() -> None:
    """50K USD at fx=32.5 → 1.625M TRY in base totals."""
    r = compute_rollup(
        [_opp(amount=50_000, currency="USD", probability=1.0, fx=32.5)],
        base_currency="TRY",
    )
    # weighted = amount * probability = 50K * 1.0 = 50K USD
    # base_weighted = 50K * 32.5 = 1_625_000 TRY
    assert r.base_total_weighted == Decimal("1625000.00000000")
    assert r.base_total_has_estimates is False


def test_base_currency_flags_estimate_when_fx_missing() -> None:
    """Cross-currency opp without fx_rate falls back to 1.0 and
    raises the estimate flag for the UI."""
    r = compute_rollup(
        [_opp(amount=100_000, currency="USD", probability=0.5, fx=None)],
        base_currency="TRY",
    )
    assert r.base_total_has_estimates is True
    # 100K * 0.5 * 1.0 (fallback) = 50K
    assert r.base_total_weighted == Decimal("50000")


def test_same_currency_never_flags_estimate() -> None:
    """Same-currency opps don't need fx_rate; no flag."""
    r = compute_rollup(
        [_opp(amount=100_000, currency="TRY", probability=0.5, fx=None)],
        base_currency="TRY",
    )
    assert r.base_total_has_estimates is False


def test_rollup_serialisation_round_to_2_decimal() -> None:
    r = compute_rollup(
        [_opp(amount=Decimal("99.999"), currency="TRY", probability=0.5)],
        base_currency="TRY",
    )
    d = r.as_dict()
    # 99.999 * 0.5 = 49.9995 → banker's rounds to 50.00
    assert d["by_currency"]["TRY"]["weighted_amount"] == "50.00"


def test_empty_input_returns_zero_rollup() -> None:
    r = compute_rollup([], base_currency="TRY")
    assert r.by_currency == {}
    assert r.base_total_open == Decimal(0)


# ────────────────────────────────────────────────────────────────────
# F-014 — Health-recompute debouncer (in-process)
# ────────────────────────────────────────────────────────────────────


from app.services.health_recompute_debouncer import (
    _DirtySet,
    drain,
    mark_dirty,
    queue_size,
    reset_for_tests,
    run_batch_recompute,
)


def setup_function() -> None:
    """Each F-014 test starts with a clean queue."""
    reset_for_tests()


def test_mark_dirty_dedupes_within_window() -> None:
    """1000 marks for the same customer → 1 entry."""
    for _ in range(1000):
        mark_dirty(42)
    assert queue_size() == 1


def test_mark_dirty_different_customers_accumulate() -> None:
    for cid in range(1, 101):
        mark_dirty(cid)
    assert queue_size() == 100


def test_drain_returns_and_clears() -> None:
    mark_dirty(1)
    mark_dirty(2)
    drained = drain()
    assert set(drained) == {1, 2}
    assert queue_size() == 0


def test_drain_idempotent_when_empty() -> None:
    assert drain() == []
    assert drain() == []


def test_dirty_set_evicts_lru_at_cap() -> None:
    """LRU eviction at capacity protects against runaway sources."""
    ds = _DirtySet(max_size=3, ttl=60)
    ds.mark(1)
    ds.mark(2)
    ds.mark(3)
    ds.mark(4)        # should evict 1
    drained = ds.drain()
    assert set(drained) == {2, 3, 4}


def test_dirty_set_evicts_stale_on_drain() -> None:
    """Past-TTL entries are dropped on drain (with a warning, but the
    drain still succeeds with the live IDs)."""
    import time as _time

    ds = _DirtySet(max_size=10, ttl=1)
    ds.mark(1)
    _time.sleep(1.1)
    ds.mark(2)
    drained = ds.drain()
    # Only the fresh one survives; stale ID 1 is dropped silently
    # (with a warning at log level — checked via caplog in a
    # real-life harness).
    assert set(drained) == {2}


def test_mark_dirty_ignores_none() -> None:
    mark_dirty(None)
    assert queue_size() == 0


def test_run_batch_recompute_calls_for_each_id() -> None:
    """The batch worker invokes the injected recompute_fn once per ID."""
    mark_dirty(7)
    mark_dirty(8)
    seen: list[int] = []

    async def fake_recompute(db, cid):
        seen.append(cid)

    result = asyncio.get_event_loop().run_until_complete(
        run_batch_recompute(db=None, recompute_fn=fake_recompute)
    )
    assert result == 2
    assert set(seen) == {7, 8}


def test_run_batch_recompute_tolerates_per_id_failure() -> None:
    """One bad customer doesn't poison the whole batch."""
    mark_dirty(1)
    mark_dirty(2)
    mark_dirty(3)
    seen: list[int] = []

    async def fake_recompute(db, cid):
        if cid == 2:
            raise RuntimeError("boom")
        seen.append(cid)

    result = asyncio.get_event_loop().run_until_complete(
        run_batch_recompute(db=None, recompute_fn=fake_recompute)
    )
    assert result == 2          # 1 and 3 succeeded
    assert set(seen) == {1, 3}
