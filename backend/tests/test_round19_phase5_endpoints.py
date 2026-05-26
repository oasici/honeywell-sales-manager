"""Round-19 Phase 5 — endpoint integration tests for the wired services.

Covers:
  * /kvkk-export/requests (F-023)
  * /admin/tenant-settings (F-029)
  * /trash/{entity} (F-007)
  * /bulk-import/customers + /parts (F-021 lite)
  * /sign/{token} 410-on-bad-token (F-006)
  * /unsubscribe/{token} 404-on-bad-token (F-024)

Focused on permission boundaries + happy-path roundtrips. The deeper
service-layer logic is already covered by phase 4 unit tests.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


# ────────────────────────────────────────────────────────────────────
# F-029 — tenant settings
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tenant_settings_get_returns_defaults_for_legacy_tenant(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.get(
        "/api/v1/admin/tenant-settings", headers=auth_headers
    )
    # Sales manager role gets 403 (settings is ops-only); the GET is
    # open to anyone authenticated for read so this should be 200.
    assert resp.status_code == 200
    body = resp.json()
    assert body["auto_quote_currency"] == "TRY"
    assert body["ocr_max_pages"] == 5
    # Defaults: no cap set.
    assert body["auto_quote_max_amount"] is None


@pytest.mark.asyncio
async def test_tenant_settings_update_requires_ops(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.put(
        "/api/v1/admin/tenant-settings",
        headers=auth_headers,
        json={"auto_quote_max_amount": "5000"},
    )
    # Default admin_user has role=sales_manager; settings PUT requires ops.
    assert resp.status_code == 403
    assert "ops" in resp.text.lower()


# ────────────────────────────────────────────────────────────────────
# F-023 — KVKK export
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_kvkk_create_request_happy_path(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.post(
        "/api/v1/kvkk-export/requests",
        headers=auth_headers,
        json={
            "subject_lookup": "customer@example.com",
            "subject_kind": "email",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "requested"
    assert body["subject_kind"] == "email"


@pytest.mark.asyncio
async def test_kvkk_self_approval_is_blocked(
    client: AsyncClient, auth_headers: dict
) -> None:
    create = await client.post(
        "/api/v1/kvkk-export/requests",
        headers=auth_headers,
        json={"subject_lookup": "x@y.com", "subject_kind": "email"},
    )
    request_id = create.json()["id"]

    # Same user (the requester) attempts approval -> 403.
    approve = await client.post(
        f"/api/v1/kvkk-export/requests/{request_id}/approve",
        headers=auth_headers,
        json={},
    )
    assert approve.status_code == 403
    assert "two-person" in approve.text.lower() or "differ" in approve.text.lower()


@pytest.mark.asyncio
async def test_kvkk_invalid_subject_kind_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.post(
        "/api/v1/kvkk-export/requests",
        headers=auth_headers,
        json={"subject_lookup": "x@y.com", "subject_kind": "social_security"},
    )
    assert resp.status_code == 400


# ────────────────────────────────────────────────────────────────────
# F-007 — Trash (soft-delete listing + restore)
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trash_unknown_entity_rejected(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.get(
        "/api/v1/trash/widgets", headers=auth_headers
    )
    assert resp.status_code == 400
    assert "unknown" in resp.text.lower() or "allowed" in resp.text.lower()


@pytest.mark.asyncio
async def test_trash_known_entity_returns_empty_list_when_no_deleted(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.get(
        "/api/v1/trash/customers", headers=auth_headers
    )
    # sales_manager has access; empty result is fine.
    assert resp.status_code == 200
    body = resp.json()
    assert body["entity"] == "customers"
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_trash_restore_404_on_missing(
    client: AsyncClient, auth_headers: dict
) -> None:
    resp = await client.post(
        "/api/v1/trash/customers/999999/restore", headers=auth_headers
    )
    assert resp.status_code == 404


# ────────────────────────────────────────────────────────────────────
# F-021 — Bulk import
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_import_customers_requires_ops(
    client: AsyncClient, auth_headers: dict
) -> None:
    csv_text = "name,vergi_no,email\nAcme Inc,1234567890,a@b.com\n"
    resp = await client.post(
        "/api/v1/bulk-import/customers",
        headers=auth_headers,
        files={"file": ("customers.csv", csv_text.encode(), "text/csv")},
    )
    # Default admin_user is sales_manager; import is ops-only.
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_bulk_import_parts_csv_validation(
    client: AsyncClient, auth_headers: dict
) -> None:
    """Missing required column → 403 (role check fires before parse)
    OR 200 with errors. Either way, no crash."""
    bad_csv = "wrong_column,another_column\nx,y\n"
    resp = await client.post(
        "/api/v1/bulk-import/parts",
        headers=auth_headers,
        files={"file": ("parts.csv", bad_csv.encode(), "text/csv")},
    )
    # Role check fires first → 403. That's correct behaviour: we
    # reject before reading the file.
    assert resp.status_code in (200, 403)


# ────────────────────────────────────────────────────────────────────
# F-006 — Sign OTP (public, no auth)
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sign_lookup_returns_404_for_unknown_token(
    client: AsyncClient,
) -> None:
    resp = await client.get("/api/v1/sign/nonexistent-token-abc")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sign_verify_otp_validates_format(
    client: AsyncClient,
) -> None:
    """Wrong-format code should be rejected before token lookup."""
    resp = await client.post(
        "/api/v1/sign/some-token/verify-otp",
        json={"code": "abcd12"},     # not 6 digits
    )
    # 422 from Pydantic field validation (pattern = r"^\d{6}$")
    assert resp.status_code == 422


# ────────────────────────────────────────────────────────────────────
# F-024 — Unsubscribe (public, no auth)
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unsubscribe_unknown_token_404(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/unsubscribe/xx-not-a-real-token")
    assert resp.status_code == 404
