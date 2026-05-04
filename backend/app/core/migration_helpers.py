"""Idempotent ``op.create_table`` wrapper for round-4 bootstrap compat.

The v1.9.14 bootstrap migration creates all 128 tables the model
declares. Subsequent migrations that use ``op.create_table(...)``
would otherwise fail on a fresh env because the table already exists.

This helper wraps each call so it's a no-op when the table is
already present. Existing prod (where the bootstrap is itself a
no-op) sees identical behavior because the table doesn't yet exist
when the migration runs for the first time.

Lives under ``app.core`` because alembic's ``env.py`` already imports
``app.core.config``, so the project root is on ``sys.path`` by the
time any migration runs — no extra PYTHONPATH gymnastics needed.

Usage in a migration::

    from app.core.migration_helpers import create_table_if_absent

    def upgrade() -> None:
        create_table_if_absent(
            "my_new_table",
            sa.Column("id", sa.Integer, primary_key=True),
            ...
        )
"""
from __future__ import annotations

from typing import Any

from alembic import op
from sqlalchemy import inspect


def create_table_if_absent(name: str, *args: Any, **kwargs: Any) -> None:
    """``op.create_table`` that's a no-op when ``name`` already exists.

    Inspects the bound connection's catalogue. Cheap because
    ``inspect()`` caches per-bind, and there's at most one call per
    migration step.
    """
    bind = op.get_bind()
    inspector = inspect(bind)
    if name in inspector.get_table_names():
        return
    op.create_table(name, *args, **kwargs)
