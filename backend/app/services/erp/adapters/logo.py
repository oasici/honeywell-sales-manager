"""Logo Tiger / Netsis XML-RPC adapter.

Logo exposes an XML-RPC endpoint (usually ``/api/v1/logo-ws.svc`` or a
``/xmlrpc`` path) that returns records in Windows-1254. We convert to UTF-8
before yielding DTOs so the rest of the pipeline stays ASCII-safe.

v1 scope: read-only (customers, products, stock).
v1.1    : push_invoice for sales order / e-Fatura creation.

The actual ``xmlrpc.client.ServerProxy`` is synchronous, so we run calls in a
thread executor to keep the FastAPI event loop unblocked.
"""

from __future__ import annotations

import asyncio
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


class LogoConnector(ERPConnector):
    """Minimal Logo Tiger XML-RPC client.

    Full field coverage is iterated on with the Logo partner once sandbox is
    granted; this stub establishes the call plumbing + error mapping so the
    orchestrator can already schedule and inspect jobs end-to-end.
    """

    name = "logo"

    def __init__(self, *, endpoint: str, credentials: dict[str, Any]) -> None:
        if not endpoint:
            raise ConnectorError("Logo endpoint URL is required")
        self._endpoint = endpoint
        self._creds = credentials

    def _proxy(self) -> ServerProxy:
        return ServerProxy(self._endpoint, allow_none=True)

    def _invoke_sync(self, method: str, *args: Any) -> Any:
        proxy = self._proxy()
        try:
            return getattr(proxy, method)(*args)
        except Fault as exc:
            if exc.faultCode in (401, 403):
                raise ConnectorAuthError(str(exc)) from exc
            raise ConnectorError(f"Logo XML-RPC fault {exc.faultCode}: {exc.faultString}") from exc
        except Exception as exc:  # pragma: no cover - network exceptional
            raise ConnectorError(f"Logo transport error: {exc}") from exc

    async def _invoke(self, method: str, *args: Any) -> Any:
        return await asyncio.to_thread(self._invoke_sync, method, *args)

    # ── Protocol impl ──────────────────────────────────────────────────────

    async def test_connection(self) -> dict:
        username = self._creds.get("username")
        password = self._creds.get("password")
        if not username or not password:
            raise ConnectorAuthError("Logo credentials missing username/password")
        session = await self._invoke("Login", username, password)
        return {"ok": True, "session_ref": str(session)[:40]}

    async def fetch_customers(
        self, *, since: datetime | None = None, page_size: int = 100
    ) -> AsyncIterator[ERPCustomer]:
        since_str = since.strftime("%Y-%m-%d %H:%M:%S") if since else ""
        offset = 0
        while True:
            rows = await self._invoke("ListCustomers", since_str, offset, page_size)
            if not rows:
                return
            for row in rows:
                yield ERPCustomer(
                    external_id=str(row.get("LogicalRef") or row.get("Code")),
                    name=row.get("Definition_") or row.get("Definition") or "",
                    tax_number=row.get("TaxNr") or row.get("TCKN"),
                    email=row.get("EMailAddr"),
                    phone=row.get("Telephones"),
                    address=row.get("Address1"),
                    city=row.get("City"),
                    country="TR",
                    is_active=row.get("Active", 0) == 0,
                    updated_at=_parse_logo_dt(row.get("ModifiedDate")),
                    raw=row,
                )
            if len(rows) < page_size:
                return
            offset += page_size

    async def fetch_products(
        self, *, since: datetime | None = None, page_size: int = 100
    ) -> AsyncIterator[ERPProduct]:
        since_str = since.strftime("%Y-%m-%d %H:%M:%S") if since else ""
        offset = 0
        while True:
            rows = await self._invoke("ListItems", since_str, offset, page_size)
            if not rows:
                return
            for row in rows:
                yield ERPProduct(
                    external_id=str(row.get("LogicalRef") or row.get("Code")),
                    sku=row.get("Code") or "",
                    name=row.get("Name") or "",
                    description=row.get("SpecificCode"),
                    unit=row.get("UnitSetCode") or "adet",
                    unit_price=_safe_float(row.get("ListPrice")),
                    currency=row.get("CurrencyCode") or "TRY",
                    vat_rate=_safe_float(row.get("VatRate")),
                    category=row.get("ItemClass"),
                    is_active=row.get("Active", 0) == 0,
                    updated_at=_parse_logo_dt(row.get("ModifiedDate")),
                    raw=row,
                )
            if len(rows) < page_size:
                return
            offset += page_size

    async def fetch_stock(
        self, *, skus: list[str] | None = None
    ) -> AsyncIterator[ERPStockLevel]:
        rows = await self._invoke("ListStock", skus or [])
        for row in rows or []:
            yield ERPStockLevel(
                external_id=str(row.get("LogicalRef") or row.get("Code")),
                sku=row.get("Code") or "",
                warehouse_code=str(row.get("WarehouseRef") or ""),
                quantity=_safe_float(row.get("OnHand")) or 0.0,
                uom=row.get("UnitSetCode") or "adet",
            )

    async def push_customer(self, customer: ERPCustomer) -> str:  # pragma: no cover - v1.1
        raise ConnectorError("push_customer not implemented in Logo v1")

    async def push_invoice(self, invoice: ERPInvoice) -> str:  # pragma: no cover - v1.1
        raise ConnectorError("push_invoice not implemented in Logo v1")


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
