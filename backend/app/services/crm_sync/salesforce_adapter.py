"""Salesforce REST adapter (V9 — MVP).

Uses the standard Salesforce REST API (no SDK dependency). Requires
OAuth credentials with the appropriate scopes; the ``test_credentials``
method probes ``/services/data/vXX.0/sobjects`` to validate the token.

For the V9 MVP we support two entity types:
- ``account`` ↔ Salesforce ``Account`` object
- ``opportunity`` ↔ Salesforce ``Opportunity`` object

Production hardening (refresh token rotation, bulk API for >2k records,
webhook subscriptions) is V10+ scope; this adapter ships the
contract-level surface.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

import urllib.error
import urllib.parse
import urllib.request

from app.services.crm_sync.base import (
    CRMConnectorProtocol,
    ConnectorAuthError,
    ConnectorError,
    ConnectorRateLimitError,
    ConnectorTransientError,
    ExternalRecord,
)

logger = logging.getLogger(__name__)


_API_VERSION = "v60.0"
_ENTITY_OBJECT_MAP = {
    "account": "Account",
    "opportunity": "Opportunity",
}


class SalesforceAdapter:
    """Concrete adapter implementing :class:`CRMConnectorProtocol`."""

    provider_key = "salesforce"

    def __init__(
        self,
        *,
        instance_url: str,
        access_token: str,
        timeout_seconds: float = 30.0,
        # Test mode disables the actual HTTP call so unit tests can run
        # without spinning up a Salesforce sandbox.
        test_mode: bool = False,
    ) -> None:
        self._instance_url = instance_url.rstrip("/")
        self._access_token = access_token
        self._timeout = timeout_seconds
        self._test_mode = test_mode

    # ─────────────────────── Protocol impl ───────────────────────

    def test_credentials(self, credentials: dict[str, Any]) -> bool:
        if self._test_mode:
            return bool(credentials.get("access_token"))
        try:
            self._request("GET", f"/services/data/{_API_VERSION}/sobjects")
            return True
        except ConnectorError:
            return False

    def list_records(
        self,
        *,
        entity_type: str,
        since: datetime | None = None,
        limit: int = 200,
    ) -> Iterable[ExternalRecord]:
        sobject = _ENTITY_OBJECT_MAP.get(entity_type)
        if sobject is None:
            raise ConnectorError(f"Unsupported entity_type: {entity_type}")
        if self._test_mode:
            return self._fake_list(entity_type, since=since, limit=limit)

        soql = self._build_soql(sobject, since=since, limit=limit)
        path = f"/services/data/{_API_VERSION}/query?q={urllib.parse.quote(soql)}"
        body = self._request("GET", path)
        records = body.get("records", []) if isinstance(body, dict) else []
        out: list[ExternalRecord] = []
        for rec in records:
            ext_id = str(rec.get("Id"))
            updated = rec.get("LastModifiedDate")
            out.append(
                ExternalRecord(
                    external_id=ext_id,
                    fields={k: v for k, v in rec.items() if k != "attributes"},
                    updated_at=_parse_iso(updated),
                )
            )
        return out

    def push_record(
        self,
        *,
        entity_type: str,
        payload: dict[str, Any],
        external_id: str | None = None,
    ) -> str:
        sobject = _ENTITY_OBJECT_MAP.get(entity_type)
        if sobject is None:
            raise ConnectorError(f"Unsupported entity_type: {entity_type}")
        if self._test_mode:
            return external_id or f"sf-{entity_type}-test-{abs(hash(json.dumps(payload, sort_keys=True))) % 10_000}"

        if external_id:
            path = f"/services/data/{_API_VERSION}/sobjects/{sobject}/{external_id}"
            self._request("PATCH", path, body=payload)
            return external_id
        path = f"/services/data/{_API_VERSION}/sobjects/{sobject}"
        body = self._request("POST", path, body=payload)
        if not isinstance(body, dict) or "id" not in body:
            raise ConnectorError("Salesforce did not return an id on create")
        return str(body["id"])

    # ─────────────────────── helpers ─────────────────────────────

    def _build_soql(
        self, sobject: str, *, since: datetime | None, limit: int
    ) -> str:
        fields = "Id, Name, LastModifiedDate"
        if sobject == "Opportunity":
            fields = (
                "Id, Name, StageName, Amount, CloseDate, AccountId, "
                "OwnerId, LastModifiedDate"
            )
        elif sobject == "Account":
            fields = "Id, Name, Industry, NumberOfEmployees, LastModifiedDate"
        soql = f"SELECT {fields} FROM {sobject}"
        if since is not None:
            soql += f" WHERE LastModifiedDate > {since.astimezone(timezone.utc).isoformat()}"
        soql += f" ORDER BY LastModifiedDate ASC LIMIT {min(int(limit), 2000)}"
        return soql

    def _request(
        self, method: str, path: str, *, body: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self._instance_url}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._access_token}")
        req.add_header("Accept", "application/json")
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read()
                if not raw:
                    return {}
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            self._raise_for_http(exc)
        except urllib.error.URLError as exc:
            raise ConnectorTransientError(str(exc)) from exc

    def _raise_for_http(self, exc: "urllib.error.HTTPError") -> None:
        code = getattr(exc, "code", 0)
        if code == 401:
            raise ConnectorAuthError("Invalid or expired Salesforce token") from exc
        if code == 429:
            raise ConnectorRateLimitError("Salesforce rate limit hit") from exc
        if 500 <= code < 600:
            raise ConnectorTransientError(f"Salesforce 5xx ({code})") from exc
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="ignore")
        except Exception:  # noqa: BLE001
            pass
        raise ConnectorError(f"Salesforce error {code}: {body[:200]}") from exc

    def _fake_list(
        self, entity_type: str, *, since: datetime | None, limit: int
    ) -> list[ExternalRecord]:
        """Deterministic stub used in unit tests."""
        out = []
        for i in range(min(3, limit)):
            out.append(
                ExternalRecord(
                    external_id=f"sf-{entity_type}-{i}",
                    fields={"Id": f"sf-{entity_type}-{i}", "Name": f"Demo {i}"},
                    updated_at=since,
                )
            )
        return out


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


# Static type assertion: SalesforceAdapter conforms to the Protocol.
_: CRMConnectorProtocol = SalesforceAdapter(
    instance_url="https://example", access_token="x", test_mode=True
)
