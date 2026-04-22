"""SAP Business One Service Layer (REST) adapter - stub for v1.1.

The Service Layer speaks OData-ish JSON. Authentication is a POST to
``/Login`` that sets a session cookie; subsequent calls must include the
cookie until ``/Logout``.
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


class SAPBusinessOneConnector(ERPConnector):
    """Placeholder SAP B1 adapter; activated in v1.1."""

    name = "sap_b1"

    def __init__(self, *, endpoint: str, credentials: dict[str, Any]) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._creds = credentials

    async def test_connection(self) -> dict:
        raise ConnectorError("SAP Business One connector is scheduled for v1.1")

    async def fetch_customers(
        self, *, since: datetime | None = None, page_size: int = 100
    ) -> AsyncIterator[ERPCustomer]:
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable]
        raise ConnectorError("SAP B1 fetch_customers not implemented")

    async def fetch_products(
        self, *, since: datetime | None = None, page_size: int = 100
    ) -> AsyncIterator[ERPProduct]:
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable]
        raise ConnectorError("SAP B1 fetch_products not implemented")

    async def fetch_stock(
        self, *, skus: list[str] | None = None
    ) -> AsyncIterator[ERPStockLevel]:
        if False:  # pragma: no cover
            yield  # type: ignore[unreachable]
        raise ConnectorError("SAP B1 fetch_stock not implemented")

    async def push_customer(self, customer: ERPCustomer) -> str:
        raise ConnectorError("SAP B1 push_customer not implemented")

    async def push_invoice(self, invoice: ERPInvoice) -> str:
        raise ConnectorError("SAP B1 push_invoice not implemented")
