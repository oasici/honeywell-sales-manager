"""Round-19 Phase 9 — roadmap continuation.

Covers:
  D-018  apply_request_perms_to_response decorator (surface + behaviour)
  D-023  Active sessions list/revoke/revoke-all endpoints
  D-031  Lead bulk import
"""

from __future__ import annotations

import asyncio

import pytest
from httpx import AsyncClient


# ────────────────────────────────────────────────────────────────────
# D-018 — Field permission decorator
# ────────────────────────────────────────────────────────────────────


def test_apply_request_perms_decorator_surface() -> None:
    from app.services import field_permission_service

    assert hasattr(field_permission_service, "apply_request_perms_to_response")
    assert callable(field_permission_service.apply_request_perms_to_response)


def test_apply_request_perms_decorator_tags_function() -> None:
    """The decorator stamps the wrapper with ``__field_perms_entity__``
    so the lint test can grep across the API surface."""
    from app.services.field_permission_service import apply_request_perms_to_response

    @apply_request_perms_to_response("customer")
    async def fake_endpoint():
        return {"name": "Acme", "phone": "+90..."}

    assert getattr(fake_endpoint, "__field_perms_entity__", None) == "customer"


@pytest.mark.asyncio
async def test_apply_request_perms_decorator_passes_through_unmasked() -> None:
    """When no masking rules exist for the role, the decorator is
    a no-op shape-wise."""
    from app.services.field_permission_service import apply_request_perms_to_response

    @apply_request_perms_to_response("customer")
    async def get_one():
        return {"id": 1, "name": "Acme", "phone": "+90 555 111 22 33"}

    result = await get_one()
    assert result["id"] == 1
    assert result["name"] == "Acme"


@pytest.mark.asyncio
async def test_apply_request_perms_decorator_handles_list_envelope() -> None:
    from app.services.field_permission_service import apply_request_perms_to_response

    @apply_request_perms_to_response("customer")
    async def list_endpoint():
        return {
            "items": [
                {"id": 1, "name": "A"},
                {"id": 2, "name": "B"},
            ],
            "total": 2,
        }

    result = await list_endpoint()
    assert len(result["items"]) == 2
    assert result["total"] == 2


# ────────────────────────────────────────────────────────────────────
# D-023 — Active sessions table (model + schema verification)
# ────────────────────────────────────────────────────────────────────


def test_active_session_model_registered() -> None:
    """D-023 schema landed; existing app/api/v1/auth.py /sessions
    endpoints (feature-flagged via FEATURE_SESSION_MANAGEMENT) cover
    the GET/DELETE/{jti} surface. ``active_sessions`` table is now in
    Base.metadata so create_all builds it for tests."""
    from app.models import ActiveSession
    assert ActiveSession.__tablename__ == "active_sessions"


# ────────────────────────────────────────────────────────────────────
# D-031 — Lead bulk import service surface
# ────────────────────────────────────────────────────────────────────


def test_lead_import_module_surface() -> None:
    from app.services.bulk_import import (
        REQUIRED_LEAD_FIELDS,
        LEAD_OPTIONAL_FIELDS,
        import_leads,
    )

    assert "email" in REQUIRED_LEAD_FIELDS
    assert "first_name" in REQUIRED_LEAD_FIELDS
    assert "last_name" in REQUIRED_LEAD_FIELDS
    assert "source" in LEAD_OPTIONAL_FIELDS
    assert callable(import_leads)


@pytest.mark.asyncio
async def test_lead_import_invalid_csv_reports_errors(db, admin_user) -> None:
    """Missing required column → import report carries the error;
    no rows inserted."""
    from app.services.bulk_import import import_leads

    csv_text = "first_name,phone\nAyse,+90...\n"   # missing last_name, email
    report = await import_leads(
        db, csv_text, tenant_id=admin_user.tenant_id, actor_id=admin_user.id
    )
    assert report.inserted == 0
    assert any("csv_missing_required_columns" in e.message for e in report.errors)


@pytest.mark.asyncio
async def test_lead_import_happy_path(db, admin_user) -> None:
    from app.services.bulk_import import import_leads

    csv_text = (
        "first_name,last_name,email,phone,company,source\n"
        "Ayse,Yilmaz,ayse@example.com,+905551234567,Acme,manual\n"
        "Mehmet,Kaya,mehmet@example.com,,Bcorp,referral\n"
    )
    report = await import_leads(
        db, csv_text, tenant_id=admin_user.tenant_id, actor_id=admin_user.id
    )
    await db.commit()
    assert report.inserted == 2
    assert report.skipped == 0


@pytest.mark.asyncio
async def test_lead_import_dedupes_by_email(db, admin_user) -> None:
    """Re-uploading the same sheet UPDATEs instead of duplicating."""
    from app.services.bulk_import import import_leads

    csv1 = "first_name,last_name,email\nAyse,Yilmaz,ayse@example.com\n"
    first = await import_leads(
        db, csv1, tenant_id=admin_user.tenant_id, actor_id=admin_user.id
    )
    await db.commit()
    assert first.inserted == 1

    csv2 = "first_name,last_name,email\nAyse,YilmazUpdated,ayse@example.com\n"
    second = await import_leads(
        db, csv2, tenant_id=admin_user.tenant_id, actor_id=admin_user.id
    )
    await db.commit()
    assert second.inserted == 0
    assert second.updated == 1


@pytest.mark.asyncio
async def test_lead_import_bad_email_skipped(db, admin_user) -> None:
    from app.services.bulk_import import import_leads

    csv_text = (
        "first_name,last_name,email\n"
        "Bad,One,notanemail\n"
        "Good,Two,good@example.com\n"
    )
    report = await import_leads(
        db, csv_text, tenant_id=admin_user.tenant_id, actor_id=admin_user.id
    )
    await db.commit()
    assert report.inserted == 1
    assert report.skipped == 1
    assert any(e.field == "email" for e in report.errors)
