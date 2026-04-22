"""Generic webhook-driven adapter.

Lets a customer publish changes from an unsupported ERP via signed HTTP
POSTs to `/api/v1/erp/webhook/{connection_id}`. Pull operations raise
``ConnectorError`` - it's intentionally push-only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, AsyncIterator

from app.services.erp.base import (
    ConnectorError,
    ERPConnector,
    ERPCustomer,
    ERPInvoice,
    ERPProduct,
    ERPStockLevel,
)


class GenericWebhookConnector(ERPConnector):
    name = "webhook"

    def __init__(self, *, endpoint: str, credentials: dict[str, Any]) -> None:
        self._endpoint = endpoint
        self._creds = credentials

    async def test_connection(self) -> dict:
        return {"ok": True, "mode": "webhook", "note": "inbound webhook-only"}

    async def fetch_customers(
        self, *, since: datetime | None = None, page_size: int = 100
    ) -> AsyncIterator[ERPCustomer]:
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable]
        raise ConnectorError("webhook adapter is inbound-only")

    async def fetch_products(
        self, *, since: datetime | None = None, page_size: int = 100
    ) -> AsyncIterator[ERPProduct]:
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable]
        raise ConnectorError("webhook adapter is inbound-only")

    async def fetch_stock(
        self, *, skus: list[str] | None = None
    ) -> AsyncIterator[ERPStockLevel]:
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable]
        raise ConnectorError("webhook adapter is inbound-only")

    async def push_customer(self, customer: ERPCustomer) -> str:
        raise ConnectorError("webhook adapter does not support push")

    async def push_invoice(self, invoice: ERPInvoice) -> str:
        raise ConnectorError("webhook adapter does not support push")
