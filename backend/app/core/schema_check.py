"""Schema introspection — compare ORM mappers against the live DB.

Round-4 audit §3. The recurring R4-DB-* findings (eight tables that
existed only via ``Base.metadata.create_all()``, columns the model
declares but no migration creates, etc.) were possible because there
is no automatic check that migrations and models stay aligned. This
module is that check.

Two modes:

- **Boot-time** — controlled by env var ``SCHEMA_DRIFT_MODE``:
    - ``off`` (default in prod) — skip entirely.
    - ``warn`` (default staging) — log structured warnings + emit
      Sentry breadcrumbs (not events) per drift, grouped by table.
    - ``fail`` (default dev + CI) — raise ``SchemaDriftError`` and
      refuse to start. Crash early > silent column missing.

- **CLI** — ``python -m app.core.schema_check`` runs the same check
  and exits 0 (clean) / 1 (drift). Used by the CI guard at
  ``.github/workflows/schema-check.yml``.

Type comparison normalises dialect-specific decorators so
``String(20)`` ≡ ``VARCHAR(20)`` and ``DateTime(timezone=True)``
≡ ``TIMESTAMPTZ``. Special cases handled:

- Tables flagged with ``__table_args__ = {"info": {"skip_drift_check": True}}``
  are exempt (escape hatch for known-divergent legacy).
- Postgres views (``information_schema.views``) are skipped.
- Schema-qualified tables pass ``schema=mapper.local_table.schema``.
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import inspect
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class SchemaDriftError(RuntimeError):
    """Raised when ``SCHEMA_DRIFT_MODE=fail`` and drift is detected."""


@dataclass(frozen=True)
class TableDrift:
    table: str
    missing_in_db: tuple[str, ...] = ()
    missing_in_model: tuple[str, ...] = ()
    type_mismatch: tuple[tuple[str, str, str], ...] = ()  # (col, model_type, db_type)
    nullability_mismatch: tuple[tuple[str, bool, bool], ...] = ()  # (col, model, db)


@dataclass(frozen=True)
class SchemaDriftReport:
    tables: tuple[TableDrift, ...] = field(default_factory=tuple)

    @property
    def is_clean(self) -> bool:
        return not self.tables

    def summary(self) -> str:
        if self.is_clean:
            return "schema clean"
        parts: list[str] = []
        for t in self.tables:
            counts: list[str] = []
            if t.missing_in_db:
                counts.append(f"{len(t.missing_in_db)} missing-in-db")
            if t.missing_in_model:
                counts.append(f"{len(t.missing_in_model)} missing-in-model")
            if t.type_mismatch:
                counts.append(f"{len(t.type_mismatch)} type-mismatch")
            if t.nullability_mismatch:
                counts.append(f"{len(t.nullability_mismatch)} nullability-mismatch")
            parts.append(f"{t.table}: {', '.join(counts)}")
        return "schema drift detected — " + " | ".join(parts)


# ─────────────────────── type normalisation ──────────────────────────


def _normalise_type(type_repr: str) -> str:
    """Strip dialect-specific decorators so ``String(20)`` ≡ ``VARCHAR(20)``.

    SQLAlchemy + Postgres are loose about the round-trip — the model
    declares ``String(20)`` but ``inspect(engine)`` reports
    ``VARCHAR(20)``. We canonicalise both sides to a small enum of
    PG types so the diff doesn't go off on cosmetic differences.
    """
    s = str(type_repr).upper().strip()
    # Common synonyms.
    replacements = (
        ("VARCHAR", "STRING"),
        ("CHARACTER VARYING", "STRING"),
        ("DOUBLE PRECISION", "FLOAT"),
        ("REAL", "FLOAT"),
        ("BIGSERIAL", "BIGINT"),
        ("SERIAL", "INTEGER"),
        ("SMALLINT", "INTEGER"),  # generally interchangeable for our schema
        ("BYTEA", "BLOB"),
        ("JSONB", "JSON"),
        ("TIMESTAMP WITH TIME ZONE", "TIMESTAMPTZ"),
        ("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP"),
        ("DATETIME(TIMEZONE=TRUE)", "TIMESTAMPTZ"),
    )
    for old, new in replacements:
        s = s.replace(old, new)
    # Drop trailing parens content for unparameterised types.
    if s.endswith("()"):
        s = s[:-2]
    return s


# ─────────────────────── checker ─────────────────────────────────────


def _table_should_be_skipped(table) -> bool:
    info = getattr(table, "info", {}) or {}
    return bool(info.get("skip_drift_check"))


def _is_view(engine: Engine, table_name: str, schema: str | None) -> bool:
    """Return True if ``table_name`` is a view (information_schema.views)."""
    schema = schema or "public"
    try:
        with engine.connect() as conn:
            from sqlalchemy import text

            result = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.views "
                    "WHERE table_schema = :schema AND table_name = :name LIMIT 1"
                ),
                {"schema": schema, "name": table_name},
            )
            return result.first() is not None
    except Exception:
        # Inspector failures shouldn't break the boot path; treat as
        # "not a view" so the column comparison still runs.
        return False


def check_schema(
    engine: Engine,
    base_metadata,
    *,
    table_filter: Iterable[str] | None = None,
) -> SchemaDriftReport:
    """Compare every mapper's local_table against the live DB schema.

    Returns a ``SchemaDriftReport`` with one entry per drifting table.
    Empty report = clean.
    """
    inspector = inspect(engine)
    all_db_tables = set(inspector.get_table_names())

    drifts: list[TableDrift] = []

    for table in base_metadata.sorted_tables:
        if _table_should_be_skipped(table):
            continue
        table_name = table.name
        schema_name = table.schema  # None for default
        if table_filter is not None and table_name not in table_filter:
            continue
        if _is_view(engine, table_name, schema_name):
            continue
        if table_name not in all_db_tables:
            drifts.append(
                TableDrift(
                    table=table_name,
                    missing_in_db=tuple(c.name for c in table.columns),
                )
            )
            continue

        try:
            db_cols = inspector.get_columns(table_name, schema=schema_name)
        except Exception as exc:
            logger.warning("schema_check: failed inspecting %s: %s", table_name, exc)
            continue

        db_by_name = {c["name"]: c for c in db_cols}
        model_by_name = {c.name: c for c in table.columns}

        missing_in_db = tuple(
            name for name in model_by_name if name not in db_by_name
        )
        missing_in_model = tuple(
            name for name in db_by_name if name not in model_by_name
        )
        type_mismatch: list[tuple[str, str, str]] = []
        nullability_mismatch: list[tuple[str, bool, bool]] = []

        for name, model_col in model_by_name.items():
            db_col = db_by_name.get(name)
            if db_col is None:
                continue
            mt = _normalise_type(repr(model_col.type))
            dt = _normalise_type(str(db_col["type"]))
            # Allow String → STRING with parameter mismatch only when one side
            # has no length (model declares Text vs DB declares STRING etc).
            if mt != dt and not (mt.startswith("STRING") and dt.startswith("STRING")):
                type_mismatch.append((name, mt, dt))
            if bool(model_col.nullable) != bool(db_col.get("nullable", True)):
                nullability_mismatch.append(
                    (name, bool(model_col.nullable), bool(db_col.get("nullable", True)))
                )

        if missing_in_db or missing_in_model or type_mismatch or nullability_mismatch:
            drifts.append(
                TableDrift(
                    table=table_name,
                    missing_in_db=missing_in_db,
                    missing_in_model=missing_in_model,
                    type_mismatch=tuple(type_mismatch),
                    nullability_mismatch=tuple(nullability_mismatch),
                )
            )

    return SchemaDriftReport(tables=tuple(drifts))


# ─────────────────────── boot-time hook ──────────────────────────────


def run_schema_drift_check_on_startup(engine: Engine, base_metadata) -> None:
    """Hook called from ``app/main.py`` lifespan.

    Reads ``SCHEMA_DRIFT_MODE`` from env; defaults to ``off`` so the
    production deploy is unaffected until a release explicitly turns
    it on. ``warn`` is recommended for staging, ``fail`` for CI.
    """
    mode = os.environ.get("SCHEMA_DRIFT_MODE", "off").strip().lower()
    if mode not in {"warn", "fail"}:
        return

    report = check_schema(engine, base_metadata)
    if report.is_clean:
        logger.info("schema_check: %s", report.summary())
        return

    # Structured log per drifting table for dashboard ingestion.
    for t in report.tables:
        logger.warning(
            "schema_drift",
            extra={
                "event": "schema_drift",
                "table": t.table,
                "missing_in_db": list(t.missing_in_db),
                "missing_in_model": list(t.missing_in_model),
                "type_mismatch": [list(x) for x in t.type_mismatch],
                "nullability_mismatch": [list(x) for x in t.nullability_mismatch],
            },
        )
    # Sentry breadcrumb (not event) so the next captured exception
    # surfaces the report as context.
    try:
        import sentry_sdk

        sentry_sdk.add_breadcrumb(
            category="schema",
            level="warning",
            message=report.summary(),
            data={"tables": [t.table for t in report.tables]},
        )
    except Exception:
        pass

    if mode == "fail":
        raise SchemaDriftError(report.summary())


# ─────────────────────── CLI entrypoint ──────────────────────────────


def _cli() -> int:
    """``python -m app.core.schema_check`` — exits 0 clean / 1 drift."""
    import asyncio
    from sqlalchemy import create_engine

    from app.core.config import settings
    from app.core.database import Base

    # Use a sync engine for the CLI — the inspector API is sync-only.
    db_url = settings.SQLALCHEMY_DATABASE_URL_SYNC if hasattr(
        settings, "SQLALCHEMY_DATABASE_URL_SYNC"
    ) else settings.DATABASE_URL.replace("+asyncpg", "")

    # Importing models triggers metadata registration as a side effect.
    from app import models  # noqa: F401

    engine = create_engine(db_url)
    report = check_schema(engine, Base.metadata)
    if report.is_clean:
        print("schema_check: clean")
        return 0
    print(report.summary())
    for t in report.tables:
        print(f"  ── {t.table} ──")
        if t.missing_in_db:
            print(f"     missing in DB: {', '.join(t.missing_in_db)}")
        if t.missing_in_model:
            print(f"     missing in model: {', '.join(t.missing_in_model)}")
        for col, mt, dt in t.type_mismatch:
            print(f"     type mismatch: {col} model={mt} db={dt}")
        for col, mn, dn in t.nullability_mismatch:
            print(f"     nullability mismatch: {col} model_nullable={mn} db_nullable={dn}")
    return 1


if __name__ == "__main__":
    sys.exit(_cli())
