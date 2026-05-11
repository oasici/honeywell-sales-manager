"""Round-11 R11-AUTH-1..4 tenant guard regression tests.

Round-10 closed write-side tenant guards on the cockpit ``POST /signals/
{id}/resolve``, ``POST /quotes`` (linked customer), notifications
``PATCH /{id}/read``, and saved-views ``DELETE /{id}``. These are
fast unit-style checks that prove the helper rejects cross-tenant
records exactly the way the patched endpoints now call it.

Integration coverage for the same endpoints lives next to the API
test suite; both layers exist on purpose so an accidental removal
of the guard call still trips at least one gate.
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


# R11-AUTH-1: POST /cockpit/signals/{id}/resolve must call
# assert_same_tenant on the signal row before flipping is_resolved.
# Pre-fix any authenticated user could resolve any signal across
# tenants because revenue_signal_service.resolve_signal() only
# filtered by signal_id.


def test_r11_auth1_cross_tenant_signal_rejected() -> None:
    user = _User(id=1, tenant_id=10)
    foreign_signal = _Record(id=99, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            foreign_signal, user, exception_cls=NotFoundException
        )


def test_r11_auth1_same_tenant_signal_allowed() -> None:
    user = _User(id=1, tenant_id=10)
    own_signal = _Record(id=99, tenant_id=10)
    assert_same_tenant(own_signal, user, exception_cls=NotFoundException)


# R11-AUTH-2: POST /quotes must validate that the linked customer
# belongs to the caller's tenant. QuoteService._validate_customer
# now takes ``tenant_id`` and raises NotFoundException when the
# customer.tenant_id is non-NULL and mismatched.


def test_r11_auth2_cross_tenant_customer_link_rejected() -> None:
    user = _User(id=1, tenant_id=10)
    foreign_customer = _Record(id=42, tenant_id=20)
    # Equivalent to the new branch inside _validate_customer.
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            foreign_customer, user, exception_cls=NotFoundException
        )


# R11-AUTH-3: notifications mark_as_read() and the read-all /
# unread-count handlers now scope queries on Notification.tenant_id
# in addition to user_id. The Notification model promoted tenant_id
# to NOT NULL in 20260514, so this is a strict equality filter.


def test_r11_auth3_cross_tenant_notification_rejected() -> None:
    user = _User(id=1, tenant_id=10)
    foreign_notification = _Record(id=5, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            foreign_notification, user, exception_cls=NotFoundException
        )


# R11-AUTH-4: saved-views DELETE / LIST / POST now scope by
# tenant_id alongside user_id. User IDs are globally unique today
# but the extra filter prevents a future user_id collision (or a
# bug elsewhere) from leaking saved-views across tenants.


def test_r11_auth4_cross_tenant_saved_view_rejected() -> None:
    user = _User(id=1, tenant_id=10)
    foreign_view = _Record(id=7, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            foreign_view, user, exception_cls=NotFoundException
        )


# Sanity: legacy single-tenant rows (tenant_id=None on either side)
# stay accessible — the helper deliberately treats NULL as wildcard
# so existing single-tenant deployments don't break post-rollout.


def test_r11_legacy_null_tenant_rows_still_allowed() -> None:
    user = _User(id=1, tenant_id=None)
    legacy = _Record(id=1, tenant_id=None)
    assert_same_tenant(legacy, user, exception_cls=NotFoundException)
