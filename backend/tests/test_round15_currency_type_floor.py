"""Round-15 F-004 — currency-shaped columns must be ``Numeric``.

Round-10 R10-DB-CCY established the convention: every column whose
name implies currency (amount, total, value, cost, revenue, budget,
mrr, price, pipeline) is ``Numeric(19, 2, asdecimal=False)`` so DB
arithmetic stays exact and Python-side stays float. ``feature_store_
daily.total_open_pipeline`` slipped past the original sweep; Round-15
F-004 closed it.

This test catches the next regression — if a new model ships a
``Mapped[float]`` column with a currency-shaped name, CI fails before
the rounding drift reaches production.

Legitimate Float exceptions (rates, percentages, scores) are
allowlisted explicitly.
"""

from __future__ import annotations

from sqlalchemy import Float, Numeric


# Currency-shaped column-name patterns. Intentionally narrow — names
# like ``value`` are too ambiguous (metric_value, value_number for
# dynamic-field storage, etc.), so we don't include them and instead
# rely on specific currency-domain hints.
_CURRENCY_HINTS = (
    "amount",
    "_total",
    "grand_total",
    "subtotal",
    "tax_amount",
    "mrr",
    "budget",
    "revenue",
    "cost",
    "pipeline",
    "price_total",
)

# (table, column) pairs that legitimately stay on Float — rates,
# percentages, scores, deltas. Each entry should have a one-line
# justification in the codebase nearby.
_ALLOWED_FLOAT_EXCEPTIONS: set[tuple[str, str]] = {
    # tax_rate is a percentage (e.g. 18.0), not a currency amount.
    ("quotes", "tax_rate"),
    ("invoices", "tax_rate"),
    # Account enrichment risk index (0-100), not currency.
    ("account_enrichments", "risk_index"),
}


def test_currency_columns_are_numeric() -> None:
    """Every currency-named ``Float`` column must move to ``Numeric``.

    Only flags columns that are *actually* declared as Float; columns
    of any other type (TEXT, VARCHAR, BOOLEAN, INTEGER, NUMERIC) are
    not the target of this check. The R10-DB-CCY convention is
    specifically about Float→Numeric promotion for money fields.
    """
    import os

    os.environ.setdefault("TEST_DATABASE_URL", "sqlite+aiosqlite:///./test.db")

    from app import models  # noqa: F401 — register all mappers
    from app.core.database import Base

    bad: list[str] = []
    for table in Base.metadata.sorted_tables:
        for column in table.columns:
            if (table.name, column.name) in _ALLOWED_FLOAT_EXCEPTIONS:
                continue
            lower = column.name.lower()
            if not any(hint in lower for hint in _CURRENCY_HINTS):
                continue
            # The target is the legacy ``Float`` declaration; once
            # promoted to ``Numeric(...)`` the column passes.
            # NB: SQLAlchemy 2.x makes ``Float`` a subclass of
            # ``Numeric``, so we test ``Float`` explicitly first.
            if isinstance(column.type, Float):
                bad.append(
                    f"{table.name}.{column.name} ({column.type})"
                )

    assert not bad, (
        "Currency-named Float columns — promote to NUMERIC(19, 2) "
        f"per R10-DB-CCY: {bad}"
    )
