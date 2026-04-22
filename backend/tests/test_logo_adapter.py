"""Integration-style tests for the Logo XML-RPC adapter.

We spin up a throwaway XML-RPC server on 127.0.0.1 that answers the exact
method names the adapter sends. That way the happy path is exercised
end-to-end (XML encode -> network -> XML decode -> DTO conversion) without
needing a real Logo partner endpoint.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from xmlrpc.server import SimpleXMLRPCServer

import pytest

from app.services.erp.adapters.logo import LogoConnector
from app.services.erp.base import ConnectorAuthError, ConnectorError


# ── Fake Logo server ─────────────────────────────────────────────────────────


class _FakeLogoServer:
    """Minimal in-process XML-RPC server that imitates Logo Tiger methods."""

    def __init__(self) -> None:
        self._server = SimpleXMLRPCServer(
            ("127.0.0.1", 0), logRequests=False, allow_none=True
        )
        self._thread: threading.Thread | None = None
        self.calls: list[tuple[str, tuple]] = []

        self._server.register_function(self._login, "Login")
        self._server.register_function(self._list_customers, "ListCustomers")
        self._server.register_function(self._list_items, "ListItems")
        self._server.register_function(self._list_stock, "ListStock")

    def start(self) -> str:
        host, port = self._server.server_address
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return f"http://{host}:{port}/"

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    # ── method handlers ──
    def _login(self, username: str, password: str) -> str:
        self.calls.append(("Login", (username, password)))
        if password == "wrong":
            from xmlrpc.client import Fault

            raise Fault(401, "Invalid credentials")
        return "session-abc-123"

    def _list_customers(self, since: str, offset: int, page_size: int) -> list[dict]:
        self.calls.append(("ListCustomers", (since, offset, page_size)))
        if offset > 0:
            return []
        return [
            {
                "LogicalRef": 101,
                "Code": "C-101",
                "Definition_": "Acme A.\u015e.",
                "TaxNr": "1234567890",
                "EMailAddr": "info@acme.com",
                "Telephones": "+902121112233",
                "Address1": "Istanbul",
                "City": "Istanbul",
                "Active": 0,
                "ModifiedDate": "2026-04-20 12:34:00",
            },
            {
                "LogicalRef": 102,
                "Code": "C-102",
                "Definition": "Contoso Ltd",  # no trailing underscore
                "TaxNr": "9876543210",
                "Active": 1,  # passive in Logo convention
                "ModifiedDate": "2026-04-21 09:00:00",
            },
        ]

    def _list_items(self, since: str, offset: int, page_size: int) -> list[dict]:
        self.calls.append(("ListItems", (since, offset, page_size)))
        if offset > 0:
            return []
        return [
            {
                "LogicalRef": 501,
                "Code": "HW-FILTER-42",
                "Name": "Filtre 42",
                "UnitSetCode": "adet",
                "ListPrice": 125.0,
                "CurrencyCode": "TRY",
                "VatRate": 20.0,
                "Active": 0,
                "ModifiedDate": "2026-04-22 10:00:00",
            }
        ]

    def _list_stock(self, skus: list[str]) -> list[dict]:
        self.calls.append(("ListStock", (tuple(skus),)))
        return [
            {
                "Code": "HW-FILTER-42",
                "WarehouseRef": 1,
                "OnHand": 7.0,
                "UnitSetCode": "adet",
            }
        ]


@pytest.fixture
def logo_server():
    server = _FakeLogoServer()
    url = server.start()
    try:
        yield url, server
    finally:
        server.stop()


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_login_returns_session(logo_server):
    url, server = logo_server
    connector = LogoConnector(
        endpoint=url, credentials={"username": "demo", "password": "demo"}
    )
    result = await connector.test_connection()
    assert result["ok"] is True
    assert result["session_ref"].startswith("session-abc")
    assert any(call[0] == "Login" for call in server.calls)


@pytest.mark.asyncio
async def test_login_wrong_password_raises_auth(logo_server):
    url, _ = logo_server
    connector = LogoConnector(
        endpoint=url, credentials={"username": "demo", "password": "wrong"}
    )
    with pytest.raises(ConnectorAuthError):
        await connector.test_connection()


@pytest.mark.asyncio
async def test_fetch_customers_maps_fields_and_handles_both_definition_keys(logo_server):
    url, server = logo_server
    connector = LogoConnector(
        endpoint=url, credentials={"username": "demo", "password": "demo"}
    )
    collected = []
    async for customer in connector.fetch_customers(page_size=10):
        collected.append(customer)

    assert len(collected) == 2
    assert collected[0].external_id == "101"
    assert collected[0].name == "Acme A.\u015e."
    assert collected[0].tax_number == "1234567890"
    assert collected[0].is_active is True
    # Second row uses "Definition" without trailing underscore and is passive.
    assert collected[1].name == "Contoso Ltd"
    assert collected[1].is_active is False
    # Pagination: asked page_size=10 and got 2 rows, no second call.
    customer_calls = [call for call in server.calls if call[0] == "ListCustomers"]
    assert len(customer_calls) == 1


@pytest.mark.asyncio
async def test_fetch_customers_uses_since_when_delta(logo_server):
    url, server = logo_server
    connector = LogoConnector(
        endpoint=url, credentials={"username": "demo", "password": "demo"}
    )
    since = datetime(2026, 4, 1, tzinfo=timezone.utc)
    async for _ in connector.fetch_customers(since=since, page_size=10):
        break
    call = [c for c in server.calls if c[0] == "ListCustomers"][0]
    assert call[1][0].startswith("2026-04-01")


@pytest.mark.asyncio
async def test_fetch_products_maps_unit_price_and_currency(logo_server):
    url, _ = logo_server
    connector = LogoConnector(
        endpoint=url, credentials={"username": "demo", "password": "demo"}
    )
    products = [p async for p in connector.fetch_products(page_size=5)]
    assert products and products[0].sku == "HW-FILTER-42"
    assert products[0].unit_price == 125.0
    assert products[0].currency == "TRY"


@pytest.mark.asyncio
async def test_fetch_stock_maps_warehouse_and_qty(logo_server):
    url, _ = logo_server
    connector = LogoConnector(
        endpoint=url, credentials={"username": "demo", "password": "demo"}
    )
    readings = [s async for s in connector.fetch_stock(skus=["HW-FILTER-42"])]
    assert readings and readings[0].quantity == 7.0
    assert readings[0].warehouse_code == "1"


@pytest.mark.asyncio
async def test_unknown_method_surfaces_connector_error():
    """Partner endpoint missing a required method must raise ConnectorError."""
    server = SimpleXMLRPCServer(("127.0.0.1", 0), logRequests=False, allow_none=True)
    server.register_function(lambda u, p: "ok", "Login")
    host, port = server.server_address
    url = f"http://{host}:{port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connector = LogoConnector(endpoint=url, credentials={"username": "x", "password": "y"})
        await connector.test_connection()  # Login works
        with pytest.raises(ConnectorError):
            async for _ in connector.fetch_customers(page_size=5):
                break
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.asyncio
async def test_method_overrides_applied():
    """Custom method names in credentials route to the overridden XML-RPC method."""
    server = SimpleXMLRPCServer(("127.0.0.1", 0), logRequests=False, allow_none=True)
    calls: list[str] = []

    def _login(u, p):
        calls.append("customLogin")
        return "tok"

    def _list_customers(s, o, l):
        calls.append("wsListCari")
        return []

    server.register_function(_login, "customLogin")
    server.register_function(_list_customers, "wsListCari")
    host, port = server.server_address
    url = f"http://{host}:{port}/"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        connector = LogoConnector(
            endpoint=url,
            credentials={
                "username": "x",
                "password": "y",
                "method_overrides": {"login": "customLogin", "list_customers": "wsListCari"},
            },
        )
        await connector.test_connection()
        async for _ in connector.fetch_customers(page_size=5):
            break
        assert "customLogin" in calls
        assert "wsListCari" in calls
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.unit
def test_rejects_bad_endpoint_scheme():
    with pytest.raises(ConnectorError):
        LogoConnector(endpoint="ftp://wrong", credentials={})
    with pytest.raises(ConnectorError):
        LogoConnector(endpoint="", credentials={})
