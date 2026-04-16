"""Event bus tests — subscribe, publish, handler isolation."""

from __future__ import annotations

import pytest

from app.core.event_bus import EventBus


@pytest.fixture
def bus() -> EventBus:
    """Fresh event bus for each test — no shared state."""
    return EventBus()


@pytest.mark.asyncio
async def test_subscribe_and_publish(bus: EventBus):
    """Handler receives the event after subscribing."""
    received = []

    async def handler(event_type: str, payload: dict) -> None:
        received.append({"event_type": event_type, "payload": payload})

    bus.subscribe("order.created", handler)
    await bus.publish("order.created", {"id": 1})

    assert len(received) == 1
    assert received[0]["event_type"] == "order.created"
    assert received[0]["payload"] == {"id": 1}


@pytest.mark.asyncio
async def test_multiple_handlers(bus: EventBus):
    """All subscribed handlers are called for the same event."""
    results_a = []
    results_b = []

    async def handler_a(event_type: str, payload: dict) -> None:
        results_a.append(payload)

    async def handler_b(event_type: str, payload: dict) -> None:
        results_b.append(payload)

    bus.subscribe("deal.updated", handler_a)
    bus.subscribe("deal.updated", handler_b)
    await bus.publish("deal.updated", {"id": 42})

    assert len(results_a) == 1
    assert len(results_b) == 1


@pytest.mark.asyncio
async def test_handler_isolation_on_failure(bus: EventBus):
    """A failing handler does not prevent other handlers from running."""
    results = []

    async def failing_handler(event_type: str, payload: dict) -> None:
        raise ValueError("Simulated failure")

    async def healthy_handler(event_type: str, payload: dict) -> None:
        results.append(payload)

    bus.subscribe("test.event", failing_handler)
    bus.subscribe("test.event", healthy_handler)

    # Should not raise
    await bus.publish("test.event", {"key": "value"})

    assert len(results) == 1
    assert results[0] == {"key": "value"}


@pytest.mark.asyncio
async def test_no_handlers_for_event(bus: EventBus):
    """Publishing to an event with no handlers does nothing."""
    await bus.publish("unknown.event", {"data": True})
    # No exception — just silent no-op


@pytest.mark.asyncio
async def test_different_event_types_isolated(bus: EventBus):
    """Handlers only receive events they subscribed to."""
    received_a = []
    received_b = []

    async def handler_a(event_type: str, payload: dict) -> None:
        received_a.append(event_type)

    async def handler_b(event_type: str, payload: dict) -> None:
        received_b.append(event_type)

    bus.subscribe("event.a", handler_a)
    bus.subscribe("event.b", handler_b)

    await bus.publish("event.a", {})
    await bus.publish("event.b", {})

    assert received_a == ["event.a"]
    assert received_b == ["event.b"]


@pytest.mark.asyncio
async def test_unsubscribe(bus: EventBus):
    """Handler no longer called after unsubscribe."""
    received = []

    async def handler(event_type: str, payload: dict) -> None:
        received.append(payload)

    bus.subscribe("test.unsub", handler)
    await bus.publish("test.unsub", {"round": 1})
    assert len(received) == 1

    bus.unsubscribe("test.unsub", handler)
    await bus.publish("test.unsub", {"round": 2})
    assert len(received) == 1  # no new event


@pytest.mark.asyncio
async def test_clear_removes_all_handlers(bus: EventBus):
    """Clear removes all handlers across all event types."""
    received = []

    async def handler(event_type: str, payload: dict) -> None:
        received.append(True)

    bus.subscribe("a", handler)
    bus.subscribe("b", handler)
    assert bus.handler_count == 2

    bus.clear()
    assert bus.handler_count == 0

    await bus.publish("a", {})
    await bus.publish("b", {})
    assert len(received) == 0


@pytest.mark.asyncio
async def test_handler_count(bus: EventBus):
    """handler_count tracks total registered handlers."""
    async def noop(event_type: str, payload: dict) -> None:
        pass

    assert bus.handler_count == 0

    bus.subscribe("x", noop)
    assert bus.handler_count == 1

    bus.subscribe("x", noop)
    assert bus.handler_count == 2

    bus.subscribe("y", noop)
    assert bus.handler_count == 3


@pytest.mark.asyncio
async def test_publish_with_empty_payload(bus: EventBus):
    """Handlers receive empty dict payload without error."""
    received = []

    async def handler(event_type: str, payload: dict) -> None:
        received.append(payload)

    bus.subscribe("empty.test", handler)
    await bus.publish("empty.test", {})

    assert received == [{}]


@pytest.mark.asyncio
async def test_singleton_import():
    """The module exports a singleton event_bus instance."""
    from app.core.event_bus import event_bus

    assert isinstance(event_bus, EventBus)
