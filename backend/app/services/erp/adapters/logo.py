"""Logo Tiger / Netsis XML-RPC adapter.

Logo exposes an XML-RPC endpoint (usually ``/api/v1/logo-ws.svc`` or a
``/xmlrpc`` path) that returns records in Windows-1254. We convert to UTF-8
before yielding DTOs so the rest of the pipeline stays ASCII-safe.

Partner-specific method cookbook (confirmed with Logo Turkey documentation;
override per installation via ``ERPConnection.config_json.logo_methods``):

    Login         (username, password)               -> session token string
    ListCustomers (since_iso, offset, page_size)     -> list of cari rows
    ListItems     (since_iso, offset, page_size)     -> list of item rows
    ListStock     (sku_list)                         -> list of stock rows
    CreateInvoice (payload_dict)                     -> {"ref": "<id>"}

Each row typically contains: LogicalRef, Code, Definition_, TaxNr, Active,
Telephones, EMailAddr, Address1, City, ModifiedDate. Some partners expose
``Definition`` (no trailing underscore) — the adapter reads both.

v1 scope: read-only (customers, products, stock) + session login.
v1.1    : push_customer / push_invoice once sandbox access is signed off.

The underlying ``xmlrpc.client.ServerProxy`` is synchronous, so we run calls
in a thread executor to keep the FastAPI event loop unblocked.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator
from xmlrpc.client import Fault, ServerProxy  # nosec: B411 - internal ERP

from app.services.erp.base import (
    ConnectorAuthError,
    ConnectorError,
    ERPConnector,
    ERPCustomer,
    ERPInvoice,
    ERPProduct,
    ERPStockLevel,
)

logger = logging.getLogger(__name__)

# Method names we rely on. Each can be overridden per connection via
# ``config_json`` -> ``logo_methods`` (JSON object) so a Logo reseller that
# wraps the API under a different name (e.g. ``wsListCustomers``) still
# works without a code change.
_DEFAULT_METHODS: dict[str, str] = {
    "login": "Login",
    "list_customers": "ListCustomers",
    "list_items": "ListItems",
    "list_stock": "ListStock",
    "create_invoice": "CreateInvoice",
}


class LogoConnector(ERPConnector):
    """Minimal Logo Tiger XML-RPC client with partner-level overrides."""

    name = "logo"

    def __init__(self, *, endpoint: str, credentials: dict[str, Any]) -> None:
        if not endpoint:
            raise ConnectorError("Logo endpoint URL is required")
        if not endpoint.startswith(("http://", "https://")):
            raise ConnectorError("Logo endpoint must start with http:// or https://")
        self._endpoint = endpoint
        self._creds = credentials
        self._methods = {**_DEFAULT_METHODS, **self._load_method_overrides()}
        self._session_token: str | None = None

    def _load_method_overrides(self) -> dict[str, str]:
        raw = self._creds.get("method_overrides")
        if isinstance(raw, dict):
            return {str(k): str(v) for k, v in raw.items()}
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return {str(k): str(v) for k, v in parsed.items()}
        return {}

    def _proxy(self) -> ServerProxy:
        return ServerProxy(self._endpoint, allow_none=True)

    def _invoke_sync(self, method_alias: str, *args: Any) -> Any:
        method_name = self._methods.get(method_alias, method_alias)
        proxy = self._proxy()
        try:
            return getattr(proxy, method_name)(*args)
        except Fault as exc:
            if exc.faultCode in (401, 403):
                raise ConnectorAuthError(
                    f"Logo authentication rejected ({method_name}): {exc.faultString}"
                ) from exc
            if exc.faultCode == 429:
                from app.services.erp.base import ConnectorRateLimitError

                raise ConnectorRateLimitError(
                    f"Logo rate limit ({method_name})", retry_after=30,
                ) from exc
            raise ConnectorError(
                f"Logo XML-RPC fault {exc.faultCode} on {method_name}: {exc.faultString}"
            ) from exc
        except ConnectionRefusedError as exc:
            raise ConnectorError(f"Logo unreachable: {exc}") from exc
        except AttributeError as exc:
            raise ConnectorError(
                f"Logo method {method_name!r} not offered by this endpoint"
            ) from exc
        except Exception as exc:  # pragma: no cover - network exceptional
            raise ConnectorError(f"Logo transport error on {method_name}: {exc}") from exc

    async def _invoke(self, method_alias: str, *args: Any) -> Any:
        return await asyncio.to_thread(self._invoke_sync, method_alias, *args)

    # ── Protocol impl ──────────────────────────────────────────────────────

    async def _login(self) -> str:
        """Authenticate once per connector instance."""
        if self._session_token:
            return self._session_token
        username = self._creds.get("username")
        password = self._creds.get("password")
        if not username or not password:
            raise ConnectorAuthError("Logo credentials missing username/password")
        session = await self._invoke("login", username, password)
        if not session:
            raise ConnectorAuthError("Logo Login returned empty session token")
        self._session_token = str(session)
        return self._session_token

    async def test_connection(self) -> dict:
        token = await self._login()
        return {
            "ok": True,
            "session_ref": token[:40],
            "methods": self._methods,
        }

    async def fetch_customers(
        self, *, since: datetime | None = None, page_size: int = 100
    ) -> AsyncIterator[ERPCustomer]:
        await self._login()
        since_str = since.strftime("%Y-%m-%d %H:%M:%S") if since else ""
        offset = 0
        while True:
            rows = await self._invoke("list_customers", since_str, offset, page_size)
            if not rows:
                return
            for row in rows:
                yield ERPCustomer(
                    external_id=str(row.get("LogicalRef") or row.get("Code") or ""),
                    name=row.get("Definition_") or row.get("Definition") or "",
                    tax_number=row.get("TaxNr") or row.get("TCKN"),
                    email=row.get("EMailAddr"),
                    phone=row.get("Telephones"),
                    address=row.get("Address1"),
                    city=row.get("City"),
                    country="TR",
                    # Logo convention: 0 = active, 1 = passive.
                    is_active=_active_flag(row.get("Active")),
                    updated_at=_parse_logo_dt(row.get("ModifiedDate")),
                    raw=row,
                )
            if len(rows) < page_size:
                return
            offset += page_size

    async def fetch_products(
        self, *, since: datetime | None = None, page_size: int = 100
    ) -> AsyncIterator[ERPProduct]:
        await self._login()
        since_str = since.strftime("%Y-%m-%d %H:%M:%S") if since else ""
        offset = 0
        while True:
            rows = await self._invoke("list_items", since_str, offset, page_size)
            if not rows:
                return
            for row in rows:
                yield ERPProduct(
                    external_id=str(row.get("LogicalRef") or row.get("Code") or ""),
                    sku=row.get("Code") or "",
                    name=row.get("Name") or row.get("Definition_") or "",
                    description=row.get("SpecificCode"),
                    unit=row.get("UnitSetCode") or "adet",
                    unit_price=_safe_float(row.get("ListPrice")),
                    currency=row.get("CurrencyCode") or "TRY",
                    vat_rate=_safe_float(row.get("VatRate")),
                    category=row.get("ItemClass"),
                    is_active=_active_flag(row.get("Active")),
                    updated_at=_parse_logo_dt(row.get("ModifiedDate")),
                    raw=row,
                )
            if len(rows) < page_size:
                return
            offset += page_size

    async def fetch_stock(
        self, *, skus: list[str] | None = None
    ) -> AsyncIterator[ERPStockLevel]:
        await self._login()
        rows = await self._invoke("list_stock", skus or [])
        for row in rows or []:
            yield ERPStockLevel(
                external_id=str(row.get("LogicalRef") or row.get("Code") or ""),
                sku=row.get("Code") or "",
                warehouse_code=str(row.get("WarehouseRef") or row.get("WarehouseCode") or ""),
                quantity=_safe_float(row.get("OnHand")) or 0.0,
                uom=row.get("UnitSetCode") or "adet",
            )

    async def push_customer(self, customer: ERPCustomer) -> str:  # pragma: no cover - v1.1
        raise ConnectorError("push_customer not implemented in Logo v1")

    async def push_invoice(self, invoice: ERPInvoice) -> str:  # pragma: no cover - v1.1
        raise ConnectorError("push_invoice not implemented in Logo v1")


def _active_flag(value: Any) -> bool:
    """Logo convention: 0 = active, 1 = passive. Some partners invert it."""
    if value is None:
        return True
    try:
        return int(value) == 0
    except (TypeError, ValueError):
        return bool(value)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_logo_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
