from __future__ import annotations

import asyncio
import time

import pytest

from app.core.circuit_breaker import CircuitBreaker, CircuitOpenError


class TestCircuitBreaker:
    """Unit tests for the CircuitBreaker class."""

    @pytest.mark.asyncio
    async def test_closed_state_passes_through(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=1.0)
        assert cb.state == "closed"

        async def success():
            return "ok"

        result = await cb.call(success())
        assert result == "ok"
        assert cb.state == "closed"

    @pytest.mark.asyncio
    async def test_failures_open_circuit(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=60.0)

        async def fail():
            raise ValueError("boom")

        for _ in range(3):
            with pytest.raises(ValueError):
                await cb.call(fail())

        assert cb.state == "open"

    @pytest.mark.asyncio
    async def test_open_circuit_raises_circuit_open_error(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=60.0)

        async def fail():
            raise ValueError("boom")

        # Trigger open state
        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail())

        assert cb.state == "open"

        async def success():
            return "ok"

        with pytest.raises(CircuitOpenError, match="acik durumda"):
            await cb.call(success())

    @pytest.mark.asyncio
    async def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)

        async def fail():
            raise ValueError("boom")

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail())

        assert cb.state == "open"

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        assert cb.state == "half_open"

    @pytest.mark.asyncio
    async def test_half_open_success_closes_circuit(self):
        cb = CircuitBreaker("test", failure_threshold=2, recovery_timeout=0.1)

        async def fail():
            raise ValueError("boom")

        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail())

        await asyncio.sleep(0.15)
        assert cb.state == "half_open"

        async def success():
            return "recovered"

        result = await cb.call(success())
        assert result == "recovered"
        assert cb.state == "closed"

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens_circuit(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=0.1)

        async def fail():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            await cb.call(fail())

        assert cb.state == "open"

        await asyncio.sleep(0.15)
        assert cb.state == "half_open"

        with pytest.raises(ValueError):
            await cb.call(fail())

        assert cb.state == "open"

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", failure_threshold=3, recovery_timeout=60.0)

        async def fail():
            raise ValueError("boom")

        async def success():
            return "ok"

        # Two failures (below threshold)
        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail())

        # Success resets count
        await cb.call(success())
        assert cb._failure_count == 0

        # Two more failures should not open (count was reset)
        for _ in range(2):
            with pytest.raises(ValueError):
                await cb.call(fail())

        assert cb.state == "closed"

    def test_manual_reset(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60.0)
        cb._failure_count = 5
        cb._state = "open"
        cb._last_failure_time = time.time()

        cb.reset()

        assert cb.state == "closed"
        assert cb._failure_count == 0

    def test_is_open_property(self):
        cb = CircuitBreaker("test", failure_threshold=1, recovery_timeout=60.0)
        assert cb.is_open is False

        cb._state = "open"
        cb._last_failure_time = time.time()
        assert cb.is_open is True

    @pytest.mark.asyncio
    async def test_singleton_instances_exist(self):
        from app.core.circuit_breaker import (
            claude_breaker,
            currency_breaker,
            graph_breaker,
        )

        assert claude_breaker.name == "claude_api"
        assert claude_breaker.failure_threshold == 3
        assert graph_breaker.name == "graph_api"
        assert graph_breaker.failure_threshold == 5
        assert currency_breaker.name == "currency_api"
        assert currency_breaker.recovery_timeout == 120
