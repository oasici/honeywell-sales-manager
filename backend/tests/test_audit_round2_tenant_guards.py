"""Audit round-2 tenant guards (TEN-1, TEN-2, TEN-3).

Lightweight pure-function tests that prove the guard helpers reject
cross-tenant access. Full HTTP integration tests live alongside the
api integration suite — these are the fast unit checks we run on
every commit.

Each test exercises the exact same `assert_same_tenant` helper that
the patched endpoints now call. If a future refactor accidentally
removes one of the calls, the unit suite stays green but a sibling
integration test would catch it; both layers exist on purpose.
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


# TEN-1: bulk_action_opportunities — every fetched opportunity must
# pass assert_same_tenant before a write. The endpoint now uses
# scoped_for_user inside the SELECT, so cross-tenant rows simply
# don't appear; this test mirrors that shape.


def test_ten1_cross_tenant_opportunity_rejected():
    user = _User(id=1, tenant_id=10)
    foreign_opp = _Record(id=99, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(foreign_opp, user, exception_cls=NotFoundException)


def test_ten1_same_tenant_opportunity_passes():
    user = _User(id=1, tenant_id=10)
    own_opp = _Record(id=99, tenant_id=10)
    # Should not raise
    assert_same_tenant(own_opp, user, exception_cls=NotFoundException)


# TEN-2: approval_history — entity_type/entity_id must dispatch to
# the parent model and tenant-check the parent. The dispatcher map
# is intentionally restricted; unsupported entity_types raise 404
# (tested via the dispatcher's own behavior in the API layer).


def test_ten2_cross_tenant_quote_for_approval_history_rejected():
    user = _User(id=1, tenant_id=10)
    foreign_quote = _Record(id=42, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(foreign_quote, user, exception_cls=NotFoundException)


# TEN-3: compare_quotes — both quotes must pass assert_same_tenant
# before the role/ownership check (manager vs creator) can run.


def test_ten3_cross_tenant_quote_compare_rejected():
    user = _User(id=1, tenant_id=10)
    quote_in_other_tenant = _Record(id=7, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            quote_in_other_tenant, user, exception_cls=NotFoundException,
        )


def test_ten3_same_tenant_quote_compare_allowed():
    user = _User(id=1, tenant_id=10)
    own_quote_a = _Record(id=7, tenant_id=10)
    own_quote_b = _Record(id=8, tenant_id=10)
    assert_same_tenant(own_quote_a, user, exception_cls=NotFoundException)
    assert_same_tenant(own_quote_b, user, exception_cls=NotFoundException)


# Sanity: legacy single-tenant deployments (records and users with
# tenant_id=None) keep working without raising.


def test_legacy_single_tenant_records_still_pass():
    user = _User(id=1, tenant_id=None)
    legacy_record = _Record(id=1, tenant_id=None)
    assert_same_tenant(legacy_record, user, exception_cls=NotFoundException)
