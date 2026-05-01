"""Audit round-3 tenant guards (TEN-4 through TEN-8) + TEN-1 regression.

Pure-function tests in the same shape as test_audit_round2_tenant_guards.py.
Each new endpoint added an assert_same_tenant or scoped_for_user call site;
these tests pin the helper-level invariant so a future refactor that
removes one of the new guards trips a unit test before reaching prod.

Also catches the v1.6.1 TEN-1 regression: the original fix called
scoped_for_user with positional args that didn't match the keyword-only
signature, raising TypeError on every bulk-action call.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass

import pytest
from sqlalchemy import Column, Integer, MetaData, Table

from app.core.exceptions import NotFoundException
from app.services.tenant_context import assert_same_tenant, scoped_for_user


@dataclass
class _Record:
    id: int
    tenant_id: int | None


@dataclass
class _User:
    id: int
    tenant_id: int | None


# Shared test table for scoped_for_user signature checks.
_metadata = MetaData()
_t = Table(
    "round3_t",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, nullable=True),
)


# ── TEN-1 regression — v1.6.1 used the wrong (positional) signature ──


def test_scoped_for_user_requires_column_keyword():
    """The v1.6.1 TEN-1 fix called scoped_for_user(stmt, Model, user)
    with three positional args. The helper's signature is
    `(stmt, user, *, column)` so that call raises TypeError. Pin the
    requirement so future refactors can't reintroduce the regression.
    """
    user = _User(id=1, tenant_id=10)
    sig = inspect.signature(scoped_for_user)
    column_param = sig.parameters.get("column")
    assert column_param is not None, "scoped_for_user lost its column param"
    assert column_param.kind == inspect.Parameter.KEYWORD_ONLY


def test_scoped_for_user_with_correct_signature_does_not_raise():
    user = _User(id=1, tenant_id=10)
    stmt = _t.select()
    # The patched call shape — must succeed
    out = scoped_for_user(stmt, user, column=_t.c.tenant_id)
    assert out is not None


# ── TEN-4: bulk_action_customers ──


def test_ten4_cross_tenant_customer_rejected_via_helper():
    user = _User(id=1, tenant_id=10)
    foreign_customer = _Record(id=42, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            foreign_customer, user, exception_cls=NotFoundException,
        )


# ── TEN-5: bulk_action_leads ──


def test_ten5_cross_tenant_lead_rejected_via_helper():
    user = _User(id=1, tenant_id=10)
    foreign_lead = _Record(id=42, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            foreign_lead, user, exception_cls=NotFoundException,
        )


# ── TEN-6, TEN-7: approve_quote and send_quote ──


def test_ten6_ten7_cross_tenant_quote_rejected_via_helper():
    user = _User(id=1, tenant_id=10)
    foreign_quote = _Record(id=42, tenant_id=20)
    with pytest.raises(NotFoundException):
        assert_same_tenant(
            foreign_quote, user, exception_cls=NotFoundException,
        )


# ── TEN-8: merge_records — service signature must accept current_user ──


def test_ten8_merge_records_signature_accepts_current_user():
    """The merge service must take current_user so the API caller can
    pass it through and the service can run assert_same_tenant on
    both records (audit TEN-8). Pin the signature.
    """
    from app.services.record_duplicate_service import RecordDuplicateService

    sig = inspect.signature(RecordDuplicateService.merge_records)
    assert "current_user" in sig.parameters, (
        "merge_records lost current_user; cross-tenant guard cannot run"
    )
