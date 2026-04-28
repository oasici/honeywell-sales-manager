"""V12 multi-tenant enforcement — guard helpers + scoping behaviour.

These tests cover the *helper layer* (``is_cross_tenant`` /
``assert_same_tenant`` / ``scoped_for_user``). End-to-end API tests
live alongside the API integration suite and exercise the full
request → DB filter path. Keeping the unit tests here lets us
verify the multi-tenant invariant fast and without DB I/O.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, select

from app.services.tenant_context import (
    assert_same_tenant,
    is_cross_tenant,
    scoped_for_user,
)


# Lightweight stand-ins so we can run pure-function tests without
# needing the SQLAlchemy ORM hierarchy bootstrapped.
@dataclass
class FakeRecord:
    id: int
    tenant_id: int | None


@dataclass
class FakeUser:
    id: int
    tenant_id: int | None


# ─────────────────────── is_cross_tenant ─────────────────────────────


def test_is_cross_tenant_returns_false_for_single_tenant_deployment():
    user = FakeUser(id=1, tenant_id=None)
    record = FakeRecord(id=42, tenant_id=None)
    assert is_cross_tenant(record, user) is False


def test_is_cross_tenant_returns_false_when_user_lacks_tenant():
    user = FakeUser(id=1, tenant_id=None)
    record = FakeRecord(id=42, tenant_id=7)
    # A user without a tenant_id is treated as legacy / single-tenant
    # and must keep its existing access — flipping this to True would
    # break every deployment that hasn't run the bootstrap script yet.
    assert is_cross_tenant(record, user) is False


def test_is_cross_tenant_returns_false_when_record_lacks_tenant():
    user = FakeUser(id=1, tenant_id=7)
    record = FakeRecord(id=42, tenant_id=None)
    assert is_cross_tenant(record, user) is False


def test_is_cross_tenant_returns_true_when_tenants_differ():
    user = FakeUser(id=1, tenant_id=7)
    record = FakeRecord(id=42, tenant_id=8)
    assert is_cross_tenant(record, user) is True


def test_is_cross_tenant_returns_false_when_tenants_match():
    user = FakeUser(id=1, tenant_id=7)
    record = FakeRecord(id=42, tenant_id=7)
    assert is_cross_tenant(record, user) is False


def test_is_cross_tenant_handles_none_record():
    user = FakeUser(id=1, tenant_id=7)
    assert is_cross_tenant(None, user) is False


def test_is_cross_tenant_handles_none_user():
    record = FakeRecord(id=42, tenant_id=7)
    assert is_cross_tenant(record, None) is False


# ─────────────────────── assert_same_tenant ──────────────────────────


class _Boom(Exception):
    """Test-local exception class to verify the helper raises it."""


def test_assert_same_tenant_raises_when_cross_tenant():
    user = FakeUser(id=1, tenant_id=7)
    record = FakeRecord(id=42, tenant_id=8)
    with pytest.raises(_Boom):
        assert_same_tenant(record, user, exception_cls=_Boom)


def test_assert_same_tenant_silent_when_same_tenant():
    user = FakeUser(id=1, tenant_id=7)
    record = FakeRecord(id=42, tenant_id=7)
    # Should not raise.
    assert_same_tenant(record, user, exception_cls=_Boom)


def test_assert_same_tenant_silent_for_single_tenant_deployment():
    user = FakeUser(id=1, tenant_id=None)
    record = FakeRecord(id=42, tenant_id=None)
    assert_same_tenant(record, user, exception_cls=_Boom)


# ─────────────────────── scoped_for_user filter ──────────────────────


_metadata = MetaData()
_FakeTable = Table(
    "fake_table",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, nullable=True),
)


def test_scoped_for_user_adds_where_clause_when_user_has_tenant():
    user = FakeUser(id=1, tenant_id=7)
    stmt = select(_FakeTable.c.id)  # narrow projection so the SELECT
    # list doesn't include the tenant_id column itself — keeps the
    # assertion focused on the WHERE clause we care about.
    scoped = scoped_for_user(stmt, user, column=_FakeTable.c.tenant_id)
    compiled = str(scoped.compile(compile_kwargs={"literal_binds": True}))
    assert "WHERE" in compiled
    assert "tenant_id = 7" in compiled


def test_scoped_for_user_is_noop_when_user_tenant_is_none():
    user = FakeUser(id=1, tenant_id=None)
    stmt = select(_FakeTable.c.id)
    scoped = scoped_for_user(stmt, user, column=_FakeTable.c.tenant_id)
    compiled = str(scoped.compile(compile_kwargs={"literal_binds": True}))
    # No WHERE clause means no scoping was applied.
    assert "WHERE" not in compiled


def test_scoped_for_user_is_noop_when_user_is_none():
    stmt = select(_FakeTable.c.id)
    scoped = scoped_for_user(stmt, None, column=_FakeTable.c.tenant_id)
    compiled = str(scoped.compile(compile_kwargs={"literal_binds": True}))
    assert "WHERE" not in compiled


# ─────────────────────── bootstrap script smoke ──────────────────────


def test_bootstrap_default_tenant_module_imports():
    """The script must be importable so ops can run it via -m."""
    import importlib

    mod = importlib.import_module("scripts.bootstrap_default_tenant")
    assert hasattr(mod, "main")
    assert hasattr(mod, "main_async")
    # Ensure the core tables list matches the migration.
    assert mod._CORE_TABLES == (
        "users",
        "customers",
        "opportunities",
        "quotes",
        "leads",
    )
