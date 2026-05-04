"""In-process async event bus for record change events."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Callable

logger = logging.getLogger(__name__)

RETRY_DELAY_SECONDS = 0.1


class EventBus:
    """Simple in-process pub/sub for decoupled event handling."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[Callable]] = defaultdict(list)
        self._total_events: int = 0
        self._total_errors: int = 0
        self._handler_errors: dict[str, int] = {}

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Register a handler for an event type."""
        self._handlers[event_type].append(handler)
        logger.debug("Subscribed handler %s to event %s", handler.__name__, event_type)

    def unsubscribe(self, event_type: str, handler: Callable) -> None:
        """Remove a handler for an event type."""
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            logger.debug("Unsubscribed handler %s from event %s", handler.__name__, event_type)

    async def publish(self, event_type: str, payload: dict) -> None:
        """Publish event to all subscribers. Never raises.

        Each handler is called independently; a failing handler does not
        prevent other handlers from running. Each handler gets 1 retry
        after a brief delay on failure.
        """
        self._total_events += 1
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            logger.debug("No handlers for event %s", event_type)
            return

        for handler in handlers:
            handler_name = handler.__name__
            try:
                await handler(event_type, payload)
            except Exception:
                # Retry once after a brief delay
                try:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    await handler(event_type, payload)
                except Exception as exc:
                    self._total_errors += 1
                    self._handler_errors[handler_name] = (
                        self._handler_errors.get(handler_name, 0) + 1
                    )
                    logger.error(
                        "Event handler %s failed for %s: %s",
                        handler_name,
                        event_type,
                        exc,
                    )
                    # Forward to Sentry so silent handler failures
                    # surface on the error dashboard alongside HTTP
                    # exceptions (audit EVT-3). Wrapped in try/except
                    # because sentry_sdk may not be configured in unit
                    # tests; we never want observability to break the
                    # bus itself.
                    try:
                        import sentry_sdk

                        sentry_sdk.set_tag("event_type", event_type)
                        sentry_sdk.set_tag("handler", handler_name)
                        sentry_sdk.capture_exception(exc)
                    except Exception:
                        pass

                    # Round-4 R4-EG-1 — persist to dead_letter_events so
                    # operators can inspect + replay. Best-effort; if the
                    # DB itself is what failed, we don't want the bus to
                    # raise either. Lazy-imported because event_bus is
                    # used by tests that don't spin up the DB.
                    try:
                        await _persist_dead_letter(
                            event_type=event_type,
                            handler_name=handler_name,
                            payload=payload,
                            exc=exc,
                        )
                    except Exception:
                        logger.exception(
                            "dead-letter persist failed for %s/%s",
                            event_type,
                            handler_name,
                        )

    def clear(self) -> None:
        """Remove all handlers. Useful for testing."""
        self._handlers.clear()

    def get_stats(self) -> dict:
        """Return event bus metrics."""
        return {
            "total_events": self._total_events,
            "total_errors": self._total_errors,
            "handler_count": self.handler_count,
            "handler_errors": dict(self._handler_errors),
        }

    @property
    def handler_count(self) -> int:
        """Total number of registered handlers across all event types."""
        return sum(len(h) for h in self._handlers.values())


async def _persist_dead_letter(
    *,
    event_type: str,
    handler_name: str,
    payload: dict,
    exc: BaseException,
) -> None:
    """Insert a row into ``dead_letter_events`` for R4-EG-1.

    Imported lazily inside the function so the event_bus module stays
    importable in unit tests that don't initialise SQLAlchemy.
    """
    import json
    import traceback

    from app.core.database import async_session
    from app.models.dead_letter_event import DeadLetterEvent

    try:
        payload_str = json.dumps(payload, default=str)
    except (TypeError, ValueError):
        payload_str = repr(payload)
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))

    async with async_session() as session:
        session.add(
            DeadLetterEvent(
                event_type=event_type,
                handler_name=handler_name,
                payload_json=payload_str,
                error_message=str(exc)[:1000] or exc.__class__.__name__,
                error_traceback=tb[:8000],
                attempt_count=2,
            )
        )
        await session.commit()


# Singleton instance — import and use directly
event_bus = EventBus()
