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
    # Round-10 R10-DB-GATE — extend the gate beyond column shape.
    fk_missing_in_db: tuple[tuple[str, str, str], ...] = ()  # (column, ref_table, ref_col)
    index_missing_in_db: tuple[str, ...] = ()  # column names declared index=True or Index(...) but not present in DB
    # Round-11 R11-DB-IDX — FK columns that lack a single-column btree
    # index in the DB. Advisory only: a missing FK index is a query
    # planner concern, not a correctness bug, so this list is populated
    # but does NOT cause is_clean=False unless SCHEMA_DRIFT_STRICT_FK_INDEX=1.
    fk_columns_without_index: tuple[str, ...] = ()


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
            if t.fk_missing_in_db:
                counts.append(f"{len(t.fk_missing_in_db)} fk-missing")
            if t.index_missing_in_db:
                counts.append(f"{len(t.index_missing_in_db)} index-missing")
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
    import re

    s = str(type_repr).upper().strip()
    # Strip parameter blocks that don't affect schema equivalence.
    # PG inspector returns ``DOUBLE_PRECISION(PRECISION=53)`` and
    # ``JSON(ASTEXT_TYPE=TEXT())``; the model just declares ``Float()``
    # / ``JSON()`` — the precision/serialisation metadata is implicit
    # on the model side and explicit on the DB side. Strip these so
    # the comparison can still detect genuine type drift (FLOAT vs
    # INTEGER) without spurious noise.
    s = re.sub(r"\(\s*PRECISION\s*=\s*\d+\s*\)", "", s)
    # JSON columns: PG inspector returns ``JSON(ASTEXT_TYPE=TEXT())``
    # with a nested paren. Match the OUTER ``(...)`` block when it
    # starts with ``ASTEXT_TYPE=`` so we strip the whole metadata
    # blob rather than leaving an unbalanced trailing ``)``.
    s = re.sub(r"\(\s*ASTEXT_TYPE\s*=.*?\)\s*\)", "", s)
    # Round-10 R10-DB-CCY — Numeric(19, 2, asdecimal=False) reprs as
    # ``NUMERIC(PRECISION=19, SCALE=2, ASDECIMAL=FALSE)`` on the model
    # side; the DB inspector returns the canonical ``NUMERIC(19, 2)``.
    # `asdecimal` is a Python-side hint with no DB representation, and
    # PRECISION / SCALE are positional in PG DDL. Strip the kwarg
    # block entirely and re-emit the positional form so the two sides
    # compare cleanly.
    m = re.match(
        r"NUMERIC\(\s*PRECISION\s*=\s*(\d+)\s*,\s*SCALE\s*=\s*(\d+)(?:\s*,\s*ASDECIMAL\s*=\s*(?:TRUE|FALSE))?\s*\)",
        s,
    )
    if m:
        s = f"NUMERIC({m.group(1)}, {m.group(2)})"
    # Common synonyms.
    replacements = (
        ("VARCHAR", "STRING"),
        ("CHARACTER VARYING", "STRING"),
        ("DOUBLE_PRECISION", "FLOAT"),  # underscore form (inspector repr)
        ("DOUBLE PRECISION", "FLOAT"),  # space form (compiled DDL)
        ("REAL", "FLOAT"),
        ("BIGSERIAL", "BIGINT"),
        ("BIGINTEGER", "BIGINT"),       # SQLAlchemy BigInteger ↔ PG BIGINT
        ("SERIAL", "INTEGER"),
        ("SMALLINT", "INTEGER"),  # generally interchangeable for our schema
        ("BYTEA", "BLOB"),
        ("LARGEBINARY", "BLOB"),        # SQLAlchemy LargeBinary ↔ PG BYTEA
        ("JSONB", "JSON"),
        ("INET", "STRING"),             # PG INET ↔ String(45) for our IP columns
        ("TIMESTAMP WITH TIME ZONE", "TIMESTAMPTZ"),
        ("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP"),
        ("TIMESTAMP(TIMEZONE=TRUE)", "TIMESTAMPTZ"),
        ("TIMESTAMP(TIMEZONE=FALSE)", "TIMESTAMP"),
        ("DATETIME(TIMEZONE=TRUE)", "TIMESTAMPTZ"),
        ("DATETIME(TIMEZONE=FALSE)", "TIMESTAMP"),
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
            # Use repr() on both sides — str(DateTime(timezone=True)) is
            # lossy ('TIMESTAMP'), so the bootstrap-vs-model comparison
            # would otherwise spuriously flag every TIMESTAMPTZ column.
            mt = _normalise_type(repr(model_col.type))
            dt = _normalise_type(repr(db_col["type"]))
            # Allow String → STRING with parameter mismatch only when one side
            # has no length (model declares Text vs DB declares STRING etc).
            if mt != dt and not (mt.startswith("STRING") and dt.startswith("STRING")):
                type_mismatch.append((name, mt, dt))
            if bool(model_col.nullable) != bool(db_col.get("nullable", True)):
                nullability_mismatch.append(
                    (name, bool(model_col.nullable), bool(db_col.get("nullable", True)))
                )

        # ── Round-10 R10-DB-GATE — FK constraints ──
        # Round-9 Inv F flagged that schema_check skips FK + index
        # validation entirely, so a model change that drops/renames a
        # ForeignKey would pass CI. Compare the model's declared FKs
        # against PG's foreign_key catalogue.
        fk_missing_in_db: list[tuple[str, str, str]] = []
        try:
            db_fks = inspector.get_foreign_keys(table_name, schema=schema_name)
        except Exception:
            db_fks = []
        db_fk_pairs: set[tuple[str, str, str]] = set()
        for fk in db_fks:
            cols = fk.get("constrained_columns") or []
            ref_table = fk.get("referred_table") or ""
            ref_cols = fk.get("referred_columns") or []
            for col, ref_col in zip(cols, ref_cols):
                db_fk_pairs.add((col, ref_table, ref_col))
        for col in table.columns:
            for fk in col.foreign_keys:
                ref = fk.column
                pair = (col.name, ref.table.name, ref.name)
                if pair not in db_fk_pairs:
                    fk_missing_in_db.append(pair)

        # ── Round-10 R10-DB-GATE — declared single-column indexes ──
        # Only checks the simple `index=True` case + single-column
        # Index() entries. Composite indexes vary too much between
        # SQLAlchemy reflection and PG catalogue to compare reliably
        # here; those are caught at migration-author time.
        index_missing_in_db: list[str] = []
        try:
            db_indexes = inspector.get_indexes(table_name, schema=schema_name)
        except Exception:
            db_indexes = []
        # Set of column lists already indexed by the DB.
        db_indexed_columns: set[str] = set()
        for idx in db_indexes:
            cols = idx.get("column_names") or []
            if len(cols) == 1 and cols[0]:
                db_indexed_columns.add(cols[0])
        # PK columns are implicitly indexed; do not flag.
        try:
            pk_cols = set((inspector.get_pk_constraint(table_name, schema=schema_name) or {}).get("constrained_columns") or [])
        except Exception:
            pk_cols = set()
        # UNIQUE columns are implicitly indexed via the unique constraint.
        try:
            unique_cols = set()
            for uc in inspector.get_unique_constraints(table_name, schema=schema_name) or []:
                ucols = uc.get("column_names") or []
                if len(ucols) == 1 and ucols[0]:
                    unique_cols.add(ucols[0])
        except Exception:
            unique_cols = set()
        for col in table.columns:
            if not getattr(col, "index", False):
                continue
            if col.name in db_indexed_columns or col.name in pk_cols or col.name in unique_cols:
                continue
            index_missing_in_db.append(col.name)

        # ── Round-11 R11-DB-IDX — FK columns without an index (advisory) ──
        # A foreign key with no covering index forces a sequential scan
        # on JOIN/WHERE. Track FK columns that have neither a single-
        # column index (db_indexed_columns) nor are covered as the
        # leading column of a composite index, nor are PK/unique.
        leading_index_columns: set[str] = set(db_indexed_columns)
        for idx in db_indexes:
            cols = idx.get("column_names") or []
            if cols and cols[0]:
                leading_index_columns.add(cols[0])
        fk_columns_without_index: list[str] = []
        for col in table.columns:
            if not col.foreign_keys:
                continue
            if (
                col.name in leading_index_columns
                or col.name in pk_cols
                or col.name in unique_cols
            ):
                continue
            fk_columns_without_index.append(col.name)

        # `fk_columns_without_index` is advisory by default: only treat
        # it as drift when SCHEMA_DRIFT_STRICT_FK_INDEX=1. This lets
        # operators surface a single per-table report without breaking
        # existing CI runs that haven't backfilled every FK index.
        strict_fk_index = (
            os.environ.get("SCHEMA_DRIFT_STRICT_FK_INDEX", "").strip().lower()
            in {"1", "true", "yes"}
        )

        if (
            missing_in_db
            or missing_in_model
            or type_mismatch
            or nullability_mismatch
            or fk_missing_in_db
            or index_missing_in_db
            or (strict_fk_index and fk_columns_without_index)
        ):
            drifts.append(
                TableDrift(
                    table=table_name,
                    missing_in_db=missing_in_db,
                    missing_in_model=missing_in_model,
                    type_mismatch=tuple(type_mismatch),
                    nullability_mismatch=tuple(nullability_mismatch),
                    fk_missing_in_db=tuple(fk_missing_in_db),
                    index_missing_in_db=tuple(index_missing_in_db),
                    fk_columns_without_index=tuple(fk_columns_without_index),
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
                "fk_missing_in_db": [list(x) for x in t.fk_missing_in_db],
                "index_missing_in_db": list(t.index_missing_in_db),
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
    """``python -m app.core.schema_check`` — exits 0 clean / 1 drift.

    Uses an async engine + ``run_sync`` so the project's only PG
    driver (asyncpg) is enough — no extra psycopg dep just for the
    CLI / CI guard.
    """
    import asyncio

    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.config import settings
    from app.core.database import Base

    # Importing models triggers metadata registration as a side effect.
    from app import models  # noqa: F401

    db_url = settings.DATABASE_URL or ""
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url)

    async def _run() -> "SchemaDriftReport":
        async with engine.begin() as conn:
            return await conn.run_sync(
                lambda sync_conn: check_schema(sync_conn, Base.metadata)
            )

    report = asyncio.run(_run())
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
        for col, ref_table, ref_col in t.fk_missing_in_db:
            print(f"     fk missing in DB: {col} → {ref_table}.{ref_col}")
        for col in t.index_missing_in_db:
            print(f"     index missing in DB: {col} (model declared index=True)")
        for col in t.fk_columns_without_index:
            print(f"     fk has no covering index: {col} (advisory)")
    return 1


if __name__ == "__main__":
    sys.exit(_cli())
