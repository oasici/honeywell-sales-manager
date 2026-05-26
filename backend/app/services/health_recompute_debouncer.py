"""F-014 lite — in-process debounce for Customer Health recompute.

Pre-Round-19 a bulk import of N payments triggered N × M health
recomputes (one per per affected customer per cascaded event). At
20-30 user / single-tenant scale that's "only" a few thousand
recomputes per bulk operation — survivable on modern PG, but still
a needless DB hot-loop.

Why no Redis: at this scale a single-process in-memory dirty-set is
fine. When the deploy graduates to multi-worker (Phase 6+, Render
Pro), swap ``_DirtySet`` for a Redis SET in one place.

Contract:

  * ``mark_dirty(customer_id)`` — call from every event that should
    eventually trigger a recompute (invoice_paid, contract_renewed,
    breach_opened, etc.). Adds to the set; bounded TTL.
  * ``drain()`` — return + clear the current dirty IDs. The
    background batch worker calls this every 5 minutes and runs
    the actual recompute service on each ID.

The set caps at ``MAX_DIRTY_SIZE`` — beyond that, oldest entries
are evicted with a warning. Stale entries past TTL self-evict on
read. Both bounds protect the process from a runaway event source.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Iterable

logger = logging.getLogger(__name__)


# Tuneables. These are conservative for the 20-30 user scale; raise
# when graduating to multi-worker.
MAX_DIRTY_SIZE = 50_000
TTL_SECONDS = 60 * 60        # an entry not drained within 1h gets a warning


class _DirtySet:
    """Bounded LRU with per-entry TTL. Thread-safe.

    Single-process. Swap for Redis when multi-worker arrives — the
    public API (``mark``, ``drain``) stays unchanged.
    """

    def __init__(
        self, max_size: int = MAX_DIRTY_SIZE, ttl: int = TTL_SECONDS
    ):
        self._lock = threading.Lock()
        self._data: OrderedDict[int, float] = OrderedDict()
        self._max = max_size
        self._ttl = ttl

    def mark(self, customer_id: int) -> None:
        with self._lock:
            self._data[customer_id] = time.time()
            self._data.move_to_end(customer_id)
            if len(self._data) > self._max:
                evicted, _ = self._data.popitem(last=False)
                logger.warning(
                    "health debouncer overflow: evicted %d (cap=%d)",
                    evicted, self._max,
                )

    def drain(self) -> list[int]:
        """Return + remove the dirty IDs. Drops stale entries on the way."""
        cutoff = time.time() - self._ttl
        with self._lock:
            survivors = [cid for cid, ts in self._data.items() if ts >= cutoff]
            stale = [cid for cid, ts in self._data.items() if ts < cutoff]
            self._data.clear()
        if stale:
            logger.warning(
                "health debouncer drained %d stale IDs (TTL %ds)",
                len(stale), self._ttl,
            )
        return survivors

    def size(self) -> int:
        with self._lock:
            return len(self._data)


# Module-level singleton. Tests can monkeypatch this with a fresh
# instance — see ``test_round19_phase6_finishing.py``.
_global = _DirtySet()


def mark_dirty(customer_id: int) -> None:
    """Mark one customer as needing a health recompute.

    Call sites:
      * ``invoice_service`` when a payment is recorded.
      * ``breach_workflow`` when a new breach is opened/closed.
      * ``contract_service`` on renewal / cancellation.
      * Any event that materially changes a health-score input.

    Calling 1000 times for the same customer is fine — the set
    dedupes; the batch only runs the recompute once.
    """
    if customer_id is None:
        return
    _global.mark(int(customer_id))


def drain() -> list[int]:
    """Background worker entry point. Returns the IDs to recompute."""
    return _global.drain()


def queue_size() -> int:
    """For ``/admin/system-health`` dashboard."""
    return _global.size()


def reset_for_tests() -> None:
    """Test fixtures call this between tests."""
    global _global
    _global = _DirtySet()


async def run_batch_recompute(db, *, recompute_fn) -> int:
    """Drain the queue and call ``recompute_fn(db, customer_id)`` for
    each ID. Returns the count actually processed.

    ``recompute_fn`` is dependency-injected so tests don't need a
    real CustomerHealthService. Production wires
    ``customer_health_service.recompute_for_customer``.
    """
    ids = drain()
    processed = 0
    for cid in ids:
        try:
            await recompute_fn(db, cid)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Health recompute failed for customer %d: %s", cid, exc
            )
    if processed:
        logger.info("Health recompute batch ran: %d customers", processed)
    return processed
