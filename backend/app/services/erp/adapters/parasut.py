"""Paraşüt REST adapter (JSON:API).

Credentials dict (decrypted by factory)::

    {
      "client_id": "...",
      "client_secret": "...",
      "username": "user@example.com",
      "password": "...",
      "company_id": "12345"
    }

Endpoint override is used when Paraşüt publishes staging/sandbox bases.
The default production URL is ``https://api.parasut.com/v4``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import httpx

from app.services.erp.base import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorRateLimitError,
    ERPConnector,
    ERPCustomer,
    ERPInvoice,
    ERPProduct,
    ERPStockLevel,
)

logger = logging.getLogger(__name__)

_DEFAULT_BASE = "https://api.parasut.com/v4"
_TOKEN_URL = "https://api.parasut.com/oauth/token"
_DEFAULT_TIMEOUT = 30.0


class ParasutConnector(ERPConnector):
    name = "parasut"

    def __init__(self, *, endpoint: str, credentials: dict[str, Any]) -> None:
        self._base = (endpoint or _DEFAULT_BASE).rstrip("/")
        self._creds = credentials
        self._token: str | None = None
        self._token_expiry: datetime | None = None

    # ── Auth ───────────────────────────────────────────────────────────────

    async def _authenticate(self, client: httpx.AsyncClient) -> str:
        if self._token and self._token_expiry and self._token_expiry > datetime.now(timezone.utc):
            return self._token

        payload = {
            "grant_type": "password",
            "client_id": self._creds.get("client_id"),
            "client_secret": self._creds.get("client_secret"),
            "username": self._creds.get("username"),
            "password": self._creds.get("password"),
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        }
        resp = await client.post(_TOKEN_URL, data=payload, timeout=_DEFAULT_TIMEOUT)
        if resp.status_code in (400, 401, 403):
            raise ConnectorAuthError(f"Paraşüt auth failed: {resp.text[:200]}")
        if resp.status_code >= 500:
            raise ConnectorError(f"Paraşüt auth 5xx: {resp.status_code}")
        data = resp.json()
        self._token = data["access_token"]
        ttl = int(data.get("expires_in", 7200)) - 60
        self._token_expiry = datetime.now(timezone.utc).fromtimestamp(
            datetime.now(timezone.utc).timestamp() + ttl, tz=timezone.utc
        )
        return self._token

    def _company_url(self, path: str) -> str:
        company_id = self._creds.get("company_id")
        if not company_id:
            raise ConnectorAuthError("Paraşüt company_id missing in credentials")
        return f"{self._base}/{company_id}{path}"

    async def _request(
        self, client: httpx.AsyncClient, method: str, url: str, **kwargs: Any
    ) -> dict[str, Any]:
        token = await self._authenticate(client)
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers.setdefault("Accept", "application/json")
        resp = await client.request(method, url, headers=headers, timeout=_DEFAULT_TIMEOUT, **kwargs)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "5"))
            raise ConnectorRateLimitError("Paraşüt rate limit hit", retry_after=retry_after)
        if resp.status_code in (401, 403):
            raise ConnectorAuthError(f"Paraşüt token rejected: {resp.status_code}")
        if resp.status_code >= 400:
            raise ConnectorError(f"Paraşüt {method} {url} -> {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    # ── Protocol impl ──────────────────────────────────────────────────────

    async def test_connection(self) -> dict:
        async with httpx.AsyncClient() as client:
            await self._authenticate(client)
            data = await self._request(client, "GET", self._company_url("/contacts?page[size]=1"))
            return {"ok": True, "contacts_meta": data.get("meta", {})}

    async def fetch_customers(
        self, *, since: datetime | None = None, page_size: int = 100
    ) -> AsyncIterator[ERPCustomer]:
        page = 1
        async with httpx.AsyncClient() as client:
            while True:
                params = {
                    "page[size]": page_size,
                    "page[number]": page,
                    "filter[account_type]": "customer",
                }
                if since:
                    params["filter[last_activity_date]"] = since.strftime("%Y-%m-%d")
                url = self._company_url("/contacts")
                data = await self._request(client, "GET", url, params=params)
                records = data.get("data", [])
                if not records:
                    return
                for row in records:
                    attrs = row.get("attributes", {})
                    yield ERPCustomer(
                        external_id=str(row.get("id")),
                        name=attrs.get("name") or attrs.get("contact_type") or "",
                        tax_number=attrs.get("tax_number") or attrs.get("tckn"),
                        email=attrs.get("email"),
                        phone=attrs.get("phone"),
                        address=attrs.get("address"),
                        city=attrs.get("city"),
                        country="TR",
                        updated_at=_parse_dt(attrs.get("updated_at")),
                        raw=row,
                    )
                meta = data.get("meta", {})
                total_pages = int(meta.get("total_pages", 0) or 0)
                if total_pages and page >= total_pages:
                    return
                page += 1

    async def fetch_products(
        self, *, since: datetime | None = None, page_size: int = 100
    ) -> AsyncIterator[ERPProduct]:
        page = 1
        async with httpx.AsyncClient() as client:
            while True:
                params = {"page[size]": page_size, "page[number]": page}
                url = self._company_url("/products")
                data = await self._request(client, "GET", url, params=params)
                records = data.get("data", [])
                if not records:
                    return
                for row in records:
                    attrs = row.get("attributes", {})
                    yield ERPProduct(
                        external_id=str(row.get("id")),
                        sku=attrs.get("code") or str(row.get("id")),
                        name=attrs.get("name") or "",
                        description=attrs.get("description"),
                        unit=attrs.get("unit") or "adet",
                        unit_price=_safe_float(attrs.get("list_price")),
                        currency=attrs.get("currency") or "TRY",
                        vat_rate=_safe_float(attrs.get("vat_rate")),
                        category=attrs.get("category"),
                        updated_at=_parse_dt(attrs.get("updated_at")),
                        raw=row,
                    )
                meta = data.get("meta", {})
                total_pages = int(meta.get("total_pages", 0) or 0)
                if total_pages and page >= total_pages:
                    return
                page += 1

    async def fetch_stock(
        self, *, skus: list[str] | None = None
    ) -> AsyncIterator[ERPStockLevel]:
        # Paraşüt exposes inventory via /stock_movements; implementation pending.
        # v1 scope: return empty stream so the orchestrator can treat it as no-op.
        if False:  # pragma: no cover - async generator marker
            yield  # type: ignore[unreachable]

    async def push_customer(self, customer: ERPCustomer) -> str:
        payload = {
            "data": {
                "type": "contacts",
                "attributes": {
                    "name": customer.name,
                    "email": customer.email,
                    "tax_number": customer.tax_number,
                    "phone": customer.phone,
                    "address": customer.address,
                    "city": customer.city,
                    "account_type": "customer",
                },
            }
        }
        async with httpx.AsyncClient() as client:
            url = self._company_url("/contacts")
            if customer.external_id:
                data = await self._request(
                    client, "PUT", f"{url}/{customer.external_id}", json=payload
                )
            else:
                data = await self._request(client, "POST", url, json=payload)
            return str(data["data"]["id"])

    async def push_invoice(self, invoice: ERPInvoice) -> str:
        lines = [
            {
                "type": "sales_invoice_details",
                "attributes": {
                    "quantity": line.quantity,
                    "unit_price": line.unit_price,
                    "vat_rate": line.vat_rate,
                    "description": line.description or line.sku,
                },
            }
            for line in invoice.lines
        ]
        payload = {
            "data": {
                "type": "sales_invoices",
                "attributes": {
                    "issue_date": invoice.issue_date.strftime("%Y-%m-%d"),
                    "due_date": (invoice.due_date or invoice.issue_date).strftime("%Y-%m-%d"),
                    "currency": invoice.currency,
                    "description": invoice.notes,
                },
                "relationships": {
                    "contact": {
                        "data": {"type": "contacts", "id": invoice.customer_external_id}
                    },
                    "details": {"data": lines},
                },
            }
        }
        async with httpx.AsyncClient() as client:
            url = self._company_url("/sales_invoices")
            data = await self._request(client, "POST", url, json=payload)
            return str(data["data"]["id"])


# ── helpers ─────────────────────────────────────────────────────────────────

def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
