from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is in the open state."""

    pass


class CircuitBreaker:
    """Simple async circuit breaker for external API calls."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._state = "closed"  # closed | open | half_open

    @property
    def state(self) -> str:
        """Return the current state, transitioning open -> half_open when timeout elapses."""
        if self._state == "open":
            if time.time() - self._last_failure_time > self.recovery_timeout:
                self._state = "half_open"
        return self._state

    @property
    def is_open(self) -> bool:
        return self.state == "open"

    async def call(self, coro):
        """Execute coroutine through circuit breaker.

        Accepts either:
        - an awaitable (already-created coroutine), or
        - a zero-arg callable returning an awaitable (preferred, avoids creating
          coroutines that would never be awaited if the circuit is open).
        """
        if self.is_open:
            raise CircuitOpenError(f"Circuit breaker '{self.name}' acik durumda")

        try:
            awaitable = coro() if callable(coro) else coro
            result = await awaitable
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        self._failure_count = 0
        self._state = "closed"

    def _on_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            logger.warning(
                "Circuit breaker '%s' acildi (%d ardisik hata)",
                self.name,
                self._failure_count,
            )
            self._state = "open"

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        self._failure_count = 0
        self._state = "closed"
        self._last_failure_time = 0.0


# Singleton instances
claude_breaker = CircuitBreaker("claude_api", failure_threshold=3, recovery_timeout=30)
graph_breaker = CircuitBreaker("graph_api", failure_threshold=5, recovery_timeout=60)
currency_breaker = CircuitBreaker("currency_api", failure_threshold=5, recovery_timeout=120)
qdrant_breaker = CircuitBreaker("qdrant", failure_threshold=3, recovery_timeout=60)
