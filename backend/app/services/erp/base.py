"""Abstract ERP connector surface + shared DTOs.

Each adapter (Logo, Paraşüt, SAP Business One, Netsis, generic webhook) must
conform to the ``ERPConnector`` Protocol. Adapters return iterators over
pydantic DTOs so the orchestrator can stream large result sets without
materializing them in memory.

Turkish B2B ERPs speak dialects: Logo uses XML-RPC + Windows-1254 charset,
Paraşüt is REST + JSON:API, SAP Business One is OData-ish Service Layer.
The Protocol normalizes all of them to the shapes defined below.
"""

from __future__ import annotations

from datetime import datetime
from typing import AsyncIterator, Protocol, runtime_checkable

from pydantic import BaseModel, Field


# ── Domain DTOs ──────────────────────────────────────────────────────────────

class ERPCustomer(BaseModel):
    """Normalized customer record pulled from any ERP."""

    external_id: str = Field(..., description="ERP-native stable identifier")
    name: str
    tax_number: str | None = None  # TC/VKN
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    country: str | None = "TR"
    currency: str = "TRY"
    is_active: bool = True
    updated_at: datetime | None = None
    raw: dict = Field(default_factory=dict)  # original ERP payload for audit


class ERPProduct(BaseModel):
    """Normalized product (spare part) record."""

    external_id: str
    sku: str
    name: str
    description: str | None = None
    unit: str | None = "adet"
    unit_price: float | None = None
    currency: str = "TRY"
    vat_rate: float | None = None
    category: str | None = None
    is_active: bool = True
    updated_at: datetime | None = None
    raw: dict = Field(default_factory=dict)


class ERPStockLevel(BaseModel):
    """Point-in-time stock reading for a product at a warehouse."""

    external_id: str
    sku: str
    warehouse_code: str | None = None
    quantity: float
    uom: str | None = "adet"
    as_of: datetime | None = None


class ERPInvoiceLine(BaseModel):
    sku: str
    description: str | None = None
    quantity: float
    unit_price: float
    vat_rate: float | None = None
    line_total: float


class ERPInvoice(BaseModel):
    """Normalized invoice / e-Arsiv payload."""

    external_id: str | None = None  # None when we are pushing (ERP assigns)
    invoice_number: str | None = None
    customer_external_id: str
    issue_date: datetime
    due_date: datetime | None = None
    currency: str = "TRY"
    subtotal: float
    vat_total: float
    grand_total: float
    lines: list[ERPInvoiceLine]
    notes: str | None = None
    raw: dict = Field(default_factory=dict)


# ── Connector Protocol ───────────────────────────────────────────────────────

@runtime_checkable
class ERPConnector(Protocol):
    """Every ERP adapter conforms to this shape."""

    #: Stable short identifier ("logo", "parasut", "sap_b1", ...)
    name: str

    async def test_connection(self) -> dict:
        """Probe the ERP with a cheap call; returns diagnostic metadata.

        Implementations should raise :class:`ConnectorAuthError` for 401/403
        and :class:`ConnectorError` for other failures so the API layer can
        report a precise reason.
        """
        ...

    async def fetch_customers(
        self, *, since: datetime | None = None, page_size: int = 100
    ) -> AsyncIterator[ERPCustomer]:
        """Yield customers created/updated since ``since`` (UTC)."""
        ...

    async def fetch_products(
        self, *, since: datetime | None = None, page_size: int = 100
    ) -> AsyncIterator[ERPProduct]:
        """Yield product records created/updated since ``since``."""
        ...

    async def fetch_stock(
        self, *, skus: list[str] | None = None
    ) -> AsyncIterator[ERPStockLevel]:
        """Yield current stock readings (optionally filtered by SKU list)."""
        ...

    async def push_customer(self, customer: ERPCustomer) -> str:
        """Create or update the customer in the ERP; return external_id."""
        ...

    async def push_invoice(self, invoice: ERPInvoice) -> str:
        """Create an invoice in the ERP; return external_id."""
        ...


# ── Exceptions ───────────────────────────────────────────────────────────────

class ConnectorError(Exception):
    """Base class for all adapter-level errors."""


class ConnectorAuthError(ConnectorError):
    """Credentials missing, expired or rejected by the ERP."""


class ConnectorRateLimitError(ConnectorError):
    """ERP rate limit hit; retry after ``retry_after`` seconds."""

    def __init__(self, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ConnectorTimeoutError(ConnectorError):
    """ERP did not answer within the configured timeout."""
