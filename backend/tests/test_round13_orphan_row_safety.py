"""Round-13 R13-DB-1 — orphan-row safety for R12 nullable tenant_id columns.

The Round-12 migration ``20260518_phase12_tenant_columns`` added a
nullable ``tenant_id`` column to ``email_templates`` and
``shared_documents`` and backfilled it from ``created_by →
users.tenant_id``. Two scenarios can leave a row with
``tenant_id IS NULL`` after the backfill:

  * The creator user row was deleted before the migration ran (so the
    ``UPDATE … FROM users WHERE created_by = users.id`` join matched
    nothing).

  * The creator user existed but their ``users.tenant_id`` was itself
    NULL (legacy single-tenant deployments).

The audit flagged a theoretical leak: a tenant user listing the table
might inadvertently see those orphan rows because the SQL
``column == NULL`` comparison returns UNKNOWN, not TRUE. The current
helper ``scoped()`` adds a ``column == tenant_id`` predicate, and SQL
filters UNKNOWN rows out — so orphan rows are correctly invisible to
tenant-bound users by design.

These tests pin that behaviour against regression: someone refactoring
``scoped()`` to use ``OR column IS NULL`` (a tempting "be lenient"
change) would re-expose orphan rows across every tenant. The tests
exercise the helper directly with a synthetic statement so they don't
depend on the integration fixture stack.
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, Table, select

from app.services.tenant_context import scoped, scoped_for_user


# Minimal stand-in for an SQLAlchemy table — we don't need the ORM, just
# a Column reference the helper can attach a WHERE clause to.
_metadata = MetaData()
_orphan_safety_table = Table(
    "_orphan_safety_test",
    _metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer, nullable=True),
)


class _StubUser:
    def __init__(self, tenant_id: int | None) -> None:
        self.tenant_id = tenant_id


def _compiled_where(stmt) -> str:
    """Return the WHERE clause as a compiled string for assertion."""
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


def test_tenant_user_filter_excludes_null_tenant_rows() -> None:
    """Tenant-bound user's scoped query must filter by ``tenant_id = N``.

    SQL's three-valued logic guarantees ``tenant_id == N`` rejects rows
    where the column is NULL, so orphan rows stay invisible to a real
    tenant. This test pins the helper's compiled SQL.
    """
    base = select(_orphan_safety_table)
    stmt = scoped(base, tenant_id=10, column=_orphan_safety_table.c.tenant_id)
    sql = _compiled_where(stmt)
    assert "WHERE _orphan_safety_test.tenant_id = 10" in sql
    # The dangerous variant would also add "OR ... IS NULL". Make sure
    # we never add that clause — a refactor that introduces it would
    # re-expose every orphan row across tenants.
    assert "IS NULL" not in sql.upper().replace("NOT NULL", "")


def test_single_tenant_user_filter_is_noop() -> None:
    """Single-tenant deployments (``user.tenant_id is None``) return stmt unchanged.

    This preserves backwards compatibility for legacy installs and is
    the only case where orphan rows are legitimately visible — there's
    no tenant to scope against.
    """
    base = select(_orphan_safety_table)
    stmt = scoped(base, tenant_id=None, column=_orphan_safety_table.c.tenant_id)
    sql = _compiled_where(stmt)
    assert "WHERE" not in sql


def test_scoped_for_user_with_tenant_filters_correctly() -> None:
    """``scoped_for_user`` is the canonical entry point used by routers.

    Asserting it round-trips ``user.tenant_id`` into the WHERE clause
    catches regressions where someone bypasses ``scoped()`` and reads
    ``user.tenant_id`` directly with the wrong default.
    """
    user = _StubUser(tenant_id=42)
    base = select(_orphan_safety_table)
    stmt = scoped_for_user(
        base, user, column=_orphan_safety_table.c.tenant_id
    )
    sql = _compiled_where(stmt)
    assert "WHERE _orphan_safety_test.tenant_id = 42" in sql


def test_scoped_for_user_without_tenant_is_noop() -> None:
    """Single-tenant user: no WHERE clause added."""
    user = _StubUser(tenant_id=None)
    base = select(_orphan_safety_table)
    stmt = scoped_for_user(
        base, user, column=_orphan_safety_table.c.tenant_id
    )
    sql = _compiled_where(stmt)
    assert "WHERE" not in sql
