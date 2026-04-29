"""Redis client — RETIRED.

The project no longer uses Redis. ``get_redis()`` is kept as a
permanent ``None`` so the dozens of callers across the codebase
(JWT revocation, AI summary cache, deal health cache, field
permission cache, access service cache, etc.) continue to work
unchanged: each callsite already checks ``if r is None`` and
falls back to in-memory state.

What this means operationally:
- JWT revocation is per-worker only. A multi-worker deploy that
  needs cross-worker token revocation must enable a Redis-equivalent
  again. Single-worker / single-process deploys are unaffected.
- Caches are per-worker. Cache hits are warm only on the worker
  that filled them; cold workers hit the DB.
- Rate limiters are per-worker (already documented in
  ``rate_limit.py``). Burst spread across workers can exceed the
  configured limit by ``workers × limit``.

Why a stub instead of deleting the module:
- 39 callsites import ``get_redis``; rewriting them all in one PR
  would be a much bigger blast radius than this 25-line stub.
- Keeping the contract lets us flip Redis back on later (different
  hosted service, e.g. Upstash / KeyDB) without re-touching every
  callsite — just restore the implementation here.
"""

from __future__ import annotations


def get_redis() -> None:
    """Always returns ``None`` — Redis is no longer wired in.

    Callers must already handle the no-Redis case (the project's
    ``REDIS_URL=""`` mode predates this stub). We document the
    return type as ``None`` so downstream type-checkers narrow the
    Optional automatically.
    """
    return None


async def close_redis() -> None:
    """No-op — kept so ``main.py``'s lifespan close-path stays valid."""
    return None
