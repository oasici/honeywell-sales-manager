"""Round-12 R12-AUTH-1/2/3 tenant guard regression tests.

Round-12 closed three new cross-tenant gaps the audit flagged:

  * R12-AUTH-1 — ``EmailTemplate`` had no ``tenant_id`` column;
    ``EmailTemplateService.list_templates`` filtered only on
    ``created_by == user_id OR is_shared``, leaking every shared
    template across all tenants. ``get_template(id)`` had no filter
    at all.

  * R12-AUTH-2 — ``SharedDocument`` had no ``tenant_id`` column;
    list/analytics filtered only on ``created_by``. POST /share
    didn't verify the linked ``quote_id`` belonged to the caller's
    tenant.

  * R12-AUTH-3 — ``POST /activities/`` accepted ``opportunity_id``
    and ``customer_id`` without validating either belonged to the
    caller's tenant.

These are pure unit-style tests that drive the helper the patched
handlers now call, mirroring the R11 R11-AUTH-* pattern in
``test_round11_tenant_guards.py``. Integration coverage for the same
gaps lives next to the API test suite; both layers exist so an
accidental removal of the guard still trips at least one CI gate.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.core.exceptions import NotFoundException
from app.services.tenant_context import assert_same_tenant


@dataclass
class _Record:
    id: int
    tenant_id: int | None


@dataclass
class _User:
    id: int
    tenant_id: int | None


# R12-AUTH-1: EmailTemplate list/get/update/delete all scope on
# tenant_id in addition to the original owner/is_shared filters.
# Cross-tenant access maps to 404 (existence-leak protection).


def test_r12_auth1_cross_tenant_email_template_rejected() -> None:
    user = _User(id=1, tenant_id=10)
    foreign_template = _Record(id=42, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            foreign_template, user, exception_cls=NotFoundException
        )


def test_r12_auth1_same_tenant_email_template_allowed() -> None:
    user = _User(id=1, tenant_id=10)
    own_template = _Record(id=42, tenant_id=10)
    assert_same_tenant(own_template, user, exception_cls=NotFoundException)


# R12-AUTH-2: SharedDocument now persists tenant_id at create-time
# and filters by it on list/analytics. POST /share also calls
# assert_same_tenant on the linked quote before persisting the row.


def test_r12_auth2_cross_tenant_shared_document_rejected() -> None:
    user = _User(id=1, tenant_id=10)
    foreign_doc = _Record(id=7, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            foreign_doc, user, exception_cls=NotFoundException
        )


def test_r12_auth2_cross_tenant_quote_link_rejected() -> None:
    user = _User(id=1, tenant_id=10)
    foreign_quote = _Record(id=99, tenant_id=20)
    # Equivalent to documents.share's new pre-insert guard.
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            foreign_quote, user, exception_cls=NotFoundException
        )


# R12-AUTH-3: POST /activities/ now verifies opportunity_id and
# customer_id belong to the caller's tenant before persisting the
# ActivityLog row.


def test_r12_auth3_cross_tenant_opportunity_rejected() -> None:
    user = _User(id=1, tenant_id=10)
    foreign_opp = _Record(id=55, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            foreign_opp, user, exception_cls=NotFoundException
        )


def test_r12_auth3_cross_tenant_customer_rejected() -> None:
    user = _User(id=1, tenant_id=10)
    foreign_customer = _Record(id=77, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            foreign_customer, user, exception_cls=NotFoundException
        )


def test_r12_legacy_null_tenant_rows_still_allowed() -> None:
    """Sanity: legacy single-tenant deployments don't break."""
    user = _User(id=1, tenant_id=None)
    legacy = _Record(id=1, tenant_id=None)
    assert_same_tenant(legacy, user, exception_cls=NotFoundException)


def test_r12_tenant_id_columns_declared_on_models() -> None:
    """Verify the model classes declare ``tenant_id`` as expected.

    This is a fast structural check that catches anyone who edits the
    models and accidentally drops the column declaration. The runtime
    test above covers the behavior; this covers the declaration.
    """
    from app.models.email_template import EmailTemplate
    from app.models.shared_document import SharedDocument

    assert "tenant_id" in EmailTemplate.__table__.columns
    assert "tenant_id" in SharedDocument.__table__.columns
    # The schema_check.py gate enforces that DB == model; this test
    # only proves the model side declares the column.
