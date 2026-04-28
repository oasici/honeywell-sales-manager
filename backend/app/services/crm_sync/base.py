"""Shared types + Protocol for CRM adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Protocol, runtime_checkable


@dataclass(frozen=True)
class ExternalRecord:
    """Provider-agnostic record representation."""

    external_id: str
    fields: dict[str, Any]
    updated_at: datetime | None = None


@dataclass
class SyncResult:
    pulled: list[ExternalRecord] = field(default_factory=list)
    pushed_ids: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)


@runtime_checkable
class CRMConnectorProtocol(Protocol):
    """Adapter interface every provider implements.

    All methods are sync-callable but may run inside a thread pool
    when the underlying SDK is blocking. Adapters must raise typed
    errors (``ConnectorError`` subclasses) on auth/rate-limit/network
    failure so the orchestrator can decide retry vs. abort.
    """

    provider_key: str

    def test_credentials(self, credentials: dict[str, Any]) -> bool: ...

    def list_records(
        self, *, entity_type: str, since: datetime | None = None, limit: int = 200
    ) -> Iterable[ExternalRecord]: ...

    def push_record(
        self, *, entity_type: str, payload: dict[str, Any], external_id: str | None = None
    ) -> str: ...


class ConnectorError(Exception):
    """Base class — all adapter errors inherit from this."""


class ConnectorAuthError(ConnectorError):
    """Token expired / invalid credentials."""


class ConnectorRateLimitError(ConnectorError):
    """429 from upstream — orchestrator should back off."""


class ConnectorTransientError(ConnectorError):
    """5xx / network — safe to retry after backoff."""
