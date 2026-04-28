"""HubSpot REST adapter (V9 — MVP).

Mirrors the Salesforce adapter shape so the orchestrator can drive
either provider through the same Protocol. Uses HubSpot's CRM v3 API.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterable

from app.services.crm_sync.base import (
    CRMConnectorProtocol,
    ConnectorAuthError,
    ConnectorError,
    ConnectorRateLimitError,
    ConnectorTransientError,
    ExternalRecord,
)

logger = logging.getLogger(__name__)


_BASE_URL = "https://api.hubapi.com"
_OBJECT_PATH = {
    "account": "companies",
    "opportunity": "deals",
}


class HubSpotAdapter:
    """Concrete adapter conforming to :class:`CRMConnectorProtocol`."""

    provider_key = "hubspot"

    def __init__(
        self,
        *,
        access_token: str,
        timeout_seconds: float = 30.0,
        test_mode: bool = False,
    ) -> None:
        self._access_token = access_token
        self._timeout = timeout_seconds
        self._test_mode = test_mode

    # ─────────────────────── Protocol impl ───────────────────────

    def test_credentials(self, credentials: dict[str, Any]) -> bool:
        if self._test_mode:
            return bool(credentials.get("access_token"))
        try:
            self._request("GET", "/crm/v3/objects/companies?limit=1")
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
        path = _OBJECT_PATH.get(entity_type)
        if path is None:
            raise ConnectorError(f"Unsupported entity_type: {entity_type}")
        if self._test_mode:
            return self._fake_list(entity_type, since=since, limit=limit)

        params = {"limit": str(min(int(limit), 100))}
        if since is not None:
            ts_ms = int(since.astimezone(timezone.utc).timestamp() * 1000)
            params["properties"] = "name,hs_lastmodifieddate"
            params["after"] = str(ts_ms)
        url_path = f"/crm/v3/objects/{path}?{urllib.parse.urlencode(params)}"
        body = self._request("GET", url_path)
        results = body.get("results", []) if isinstance(body, dict) else []
        out: list[ExternalRecord] = []
        for rec in results:
            ext_id = str(rec.get("id"))
            props = rec.get("properties", {}) or {}
            out.append(
                ExternalRecord(
                    external_id=ext_id,
                    fields=props,
                    updated_at=_parse_iso(props.get("hs_lastmodifieddate")),
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
        path = _OBJECT_PATH.get(entity_type)
        if path is None:
            raise ConnectorError(f"Unsupported entity_type: {entity_type}")
        if self._test_mode:
            return external_id or f"hs-{entity_type}-test-{abs(hash(json.dumps(payload, sort_keys=True))) % 10_000}"

        envelope = {"properties": payload}
        if external_id:
            url_path = f"/crm/v3/objects/{path}/{external_id}"
            self._request("PATCH", url_path, body=envelope)
            return external_id
        url_path = f"/crm/v3/objects/{path}"
        body = self._request("POST", url_path, body=envelope)
        if not isinstance(body, dict) or "id" not in body:
            raise ConnectorError("HubSpot did not return an id on create")
        return str(body["id"])

    # ─────────────────────── HTTP plumbing ───────────────────────

    def _request(
        self, method: str, path: str, *, body: dict[str, Any] | None = None
    ) -> Any:
        url = f"{_BASE_URL}{path}"
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
            code = getattr(exc, "code", 0)
            if code == 401:
                raise ConnectorAuthError("Invalid HubSpot token") from exc
            if code == 429:
                raise ConnectorRateLimitError("HubSpot rate limit hit") from exc
            if 500 <= code < 600:
                raise ConnectorTransientError(f"HubSpot 5xx ({code})") from exc
            try:
                payload = exc.read().decode("utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                payload = ""
            raise ConnectorError(f"HubSpot error {code}: {payload[:200]}") from exc
        except urllib.error.URLError as exc:
            raise ConnectorTransientError(str(exc)) from exc

    def _fake_list(
        self, entity_type: str, *, since: datetime | None, limit: int
    ) -> list[ExternalRecord]:
        out = []
        for i in range(min(3, limit)):
            out.append(
                ExternalRecord(
                    external_id=f"hs-{entity_type}-{i}",
                    fields={"id": f"hs-{entity_type}-{i}", "name": f"HubSpot Demo {i}"},
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


_: CRMConnectorProtocol = HubSpotAdapter(access_token="x", test_mode=True)
