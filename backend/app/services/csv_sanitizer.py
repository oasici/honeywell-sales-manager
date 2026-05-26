"""F-008 — CSV / Excel formula-injection sanitiser.

Excel, LibreOffice Calc, Google Sheets, and Apple Numbers all interpret
cells whose first non-whitespace character is ``=``, ``+``, ``-``,
``@``, ``\t``, or ``\r`` as a formula. A customer named
``=cmd|'/c calc.exe'!A1`` lands in an exported CSV unescaped; opening
the file in Excel launches calc.exe. With ``=HYPERLINK(...)`` or DDE
payloads this is a one-click RCE on the operator's workstation.

OWASP guidance: prefix any such cell with a single apostrophe (``'``),
which tells the spreadsheet engine to render the value as text. The
apostrophe itself does not appear in the displayed cell.

This module is intentionally tiny + dependency-free so every exporter
(``audit.py``, ``report_engine.py``, future ``reports_v2.py`` features,
the customer/lead CSV export, the rev-rec schedule download) can drop
it in with one line.

Usage::

    from app.services.csv_sanitizer import sanitize_csv_cell, sanitize_csv_row

    writer.writerow(sanitize_csv_row(row))
    # or
    writer.writerow([sanitize_csv_cell(v) for v in row])

For XLSX (openpyxl), prefer setting ``cell.data_type = "s"`` *and*
prefixing — defence in depth.
"""

from __future__ import annotations

from typing import Iterable


_FORMULA_TRIGGERS: frozenset[str] = frozenset({"=", "+", "-", "@", "\t", "\r"})


def sanitize_csv_cell(value: object) -> str:
    """Return ``value`` as a string, prefixed if it could be a formula.

    Idempotent — a value already prefixed with a single quote is
    returned unchanged. ``None`` → empty string. Non-string scalars
    are coerced via ``str()``; only string-formula-prefixes trigger
    escaping because numeric values like ``-1.5`` are legitimate and
    not a CSV-injection vector when written via ``csv.writer`` (the
    writer surrounds them based on dialect rules).
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        # Numeric / bool / datetime / Decimal → stringify but don't
        # escape — those types render unambiguously.
        return str(value)
    if not value:
        return value
    # Strip only leading whitespace for the trigger check; we still
    # write the original whitespace back out.
    head = value.lstrip()
    if head and head[0] in _FORMULA_TRIGGERS:
        return "'" + value
    return value


def sanitize_csv_row(row: Iterable[object]) -> list[str]:
    """Apply :func:`sanitize_csv_cell` to every cell in ``row``."""
    return [sanitize_csv_cell(c) for c in row]
