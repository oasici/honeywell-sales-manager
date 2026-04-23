#!/usr/bin/env python3
"""
Kod (SQLAlchemy Base.metadata) ile Postgres public semasini karsilastirir.
DATABASE_URL zorunlu (postgresql:// veya postgresql+asyncpg://).

Kontroller (bilincli olarak "pratik" seviye):
- tablolar
- kolon isimleri
- kolon nullability
- kolon tipleri (dialect compile ile "yaklasik" kontrol)
- unique constraint (kolon seti bazinda)
- foreign key (local->remote tablo/kolon seti bazinda)
- index (kolon seti bazinda)

Cikis kodu:
- 0: uyumlu (bilinen ekstra DB tablolar haric)
- 1: sema farki var (migrate adayi / drift)
- 2: DATABASE_URL yok veya baglanti hatasi
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)


def _normalize_url(url: str) -> str:
    u = url.strip()
    if u.startswith("postgresql://"):
        return u.replace("postgresql://", "postgresql+asyncpg://", 1)
    return u


async def _main() -> int:
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        print("DATABASE_URL tanimli degil.", file=sys.stderr)
        return 2

    import app.models  # noqa: F401 — metadata dolsun
    from sqlalchemy import inspect as sa_inspect, text
    from sqlalchemy.ext.asyncio import create_async_engine

    from app.core.database import Base

    url = _normalize_url(raw)
    engine = create_async_engine(url, pool_pre_ping=True)

    meta_tables = set(Base.metadata.tables.keys())
    ignore_db_only = {"alembic_version"}

    def _coltype_string(col, dialect) -> str:
        try:
            return col.type.compile(dialect=dialect).lower()
        except Exception:
            return str(col.type).lower()

    def _is_type_compatible(db_type_s: str, exp_type_s: str) -> bool:
        """Heuristic compatibility check for common PG type synonyms."""
        dbt = (db_type_s or "").lower()
        expt = (exp_type_s or "").lower()
        if not dbt or not expt:
            return True

        # float vs double precision (SQLAlchemy Float maps to double precision on PG by default)
        if ("double precision" in dbt or "float8" in dbt) and ("float" in expt or "double" in expt):
            return True

        # varchar length: DB can be wider than model (ok)
        if ("varchar" in dbt or "character varying" in dbt) and ("varchar" in expt or "character varying" in expt):
            import re

            def _len(s: str) -> int | None:
                m = re.search(r"\((\d+)\)", s)
                return int(m.group(1)) if m else None

            dlen = _len(dbt)
            elen = _len(expt)
            if dlen is None or elen is None:
                return True
            return dlen >= elen

        # conservative: accept when either contains the other (eg 'character varying' vs 'varchar')
        return (dbt in expt) or (expt in dbt)

    async with engine.connect() as conn:
        def _snapshot(sync_conn):
            insp = sa_inspect(sync_conn)
            tables = set(insp.get_table_names(schema="public"))

            def cols_for(t: str) -> dict[str, dict]:
                if t not in tables:
                    return {}
                out: dict[str, dict] = {}
                for c in insp.get_columns(t, schema="public"):
                    out[c["name"]] = c
                return out

            colmap = {t: cols_for(t) for t in tables}

            idxmap = {t: insp.get_indexes(t, schema="public") if t in tables else [] for t in tables}
            uqmap = {
                t: insp.get_unique_constraints(t, schema="public") if t in tables else [] for t in tables
            }
            fkmap = {t: insp.get_foreign_keys(t, schema="public") if t in tables else [] for t in tables}

            return tables, colmap, idxmap, uqmap, fkmap

        try:
            db_tables, db_cols, db_indexes, db_uniques, db_fks = await conn.run_sync(_snapshot)
        except Exception as e:
            print(f"DB snapshot alinmadi: {e}", file=sys.stderr)
            await engine.dispose()
            return 2

        def _alembic(sync_conn):
            try:
                row = sync_conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
                return row[0] if row else None
            except Exception:
                return None

        alembic_rev = await conn.run_sync(_alembic)
        dialect = conn.sync_engine.dialect

    missing_tables = sorted(meta_tables - db_tables)
    extra_tables = sorted(db_tables - meta_tables - ignore_db_only)

    column_issues: list[str] = []
    type_issues: list[str] = []
    nullability_issues: list[str] = []
    index_issues: list[str] = []
    unique_issues: list[str] = []
    fk_issues: list[str] = []

    def _norm_colset(cols: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
        if not cols:
            return tuple()
        return tuple(str(c) for c in cols)

    def _norm_colset_sorted(cols: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
        if not cols:
            return tuple()
        return tuple(sorted(str(c) for c in cols))

    def _db_index_sets(t: str) -> set[tuple[str, ...]]:
        sets: set[tuple[str, ...]] = set()
        for idx in db_indexes.get(t, []) or []:
            sets.add(_norm_colset_sorted(idx.get("column_names")))
        return {s for s in sets if s}

    def _db_unique_sets(t: str) -> set[tuple[str, ...]]:
        sets: set[tuple[str, ...]] = set()
        for uq in db_uniques.get(t, []) or []:
            sets.add(_norm_colset_sorted(uq.get("column_names")))
        return {s for s in sets if s}

    def _db_fk_sets(t: str) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
        """(local_cols, referred_table, remote_cols)"""
        sets: set[tuple[tuple[str, ...], str, tuple[str, ...]]] = set()
        for fk in db_fks.get(t, []) or []:
            local = _norm_colset(fk.get("constrained_columns"))
            rtbl = str(fk.get("referred_table") or "")
            remote = _norm_colset(fk.get("referred_columns"))
            if local and rtbl and remote:
                sets.add((local, rtbl, remote))
        return sets

    # Compare per table (only for tables that exist in DB)
    for tname in sorted(meta_tables):
        if tname not in db_tables:
            continue
        table = Base.metadata.tables[tname]

        expected_cols = {c.key for c in table.columns}
        actual_cols = set((db_cols.get(tname) or {}).keys())
        miss = sorted(expected_cols - actual_cols)
        if miss:
            column_issues.append(f"  {tname}: DB'de eksik kolonlar: {', '.join(miss)}")

        # Nullability + type check (only for columns present)
        for col in table.columns:
            if col.key not in actual_cols:
                continue
            db_c = (db_cols.get(tname) or {}).get(col.key) or {}
            db_nullable = bool(db_c.get("nullable", True))
            expected_nullable = bool(col.nullable)
            if db_nullable != expected_nullable:
                nullability_issues.append(
                    f"  {tname}.{col.key}: nullable uyusmuyor (DB={db_nullable}, model={expected_nullable})"
                )

            # Tip karsilastirmasi "yaklasik": db type string'i, model compile string'inin icinde mi?
            db_type_s = str(db_c.get("type", "")).lower()
            exp_type_s = _coltype_string(col, dialect)
            if db_type_s and exp_type_s and not _is_type_compatible(db_type_s, exp_type_s):
                type_issues.append(
                    f"  {tname}.{col.key}: type uyusmuyor (DB={db_type_s}, model={exp_type_s})"
                )

        # Index sets (skip PK/unique implicit indexes; only check explicit Index objects)
        expected_idx_sets: set[tuple[str, ...]] = set()
        for idx in table.indexes:
            expected_idx_sets.add(tuple(sorted(c.name for c in idx.columns if c.name)))
        expected_idx_sets = {s for s in expected_idx_sets if s}
        db_idx_sets = _db_index_sets(tname)
        missing_idx = sorted(expected_idx_sets - db_idx_sets)
        for cols in missing_idx:
            index_issues.append(f"  {tname}: eksik index kolonlari: {', '.join(cols)}")

        # Unique constraints (column set)
        expected_uq_sets: set[tuple[str, ...]] = set()
        for cons in table.constraints:
            if cons.__class__.__name__ == "UniqueConstraint":
                expected_uq_sets.add(tuple(sorted(c.name for c in cons.columns if c.name)))
        expected_uq_sets = {s for s in expected_uq_sets if s}
        db_uq_sets = _db_unique_sets(tname)
        missing_uq = sorted(expected_uq_sets - db_uq_sets)
        for cols in missing_uq:
            unique_issues.append(f"  {tname}: eksik unique kolonlari: {', '.join(cols)}")

        # Foreign keys (local->remote)
        expected_fk_sets: set[tuple[tuple[str, ...], str, tuple[str, ...]]] = set()
        for fk in table.foreign_key_constraints:
            local = tuple(fk.column_keys)
            rtbl = fk.referred_table.name if fk.referred_table is not None else ""
            remote = tuple([e.column.name for e in fk.elements if e.column is not None])
            if local and rtbl and remote:
                expected_fk_sets.add((local, rtbl, remote))
        db_fk_sets = _db_fk_sets(tname)
        missing_fk = sorted(expected_fk_sets - db_fk_sets)
        for local, rtbl, remote in missing_fk:
            fk_issues.append(
                f"  {tname}: eksik FK ({', '.join(local)} -> {rtbl}({', '.join(remote)}))"
            )

    await engine.dispose()

    print("--- Alembic ---")
    print(f"alembic_version (DB): {alembic_rev or '(yok / okunamadi)'}")
    print("--- Tablolar ---")
    print(f"Model tablo sayisi: {len(meta_tables)}")
    print(f"DB public tablo sayisi: {len(db_tables)}")
    if extra_tables:
        print(f"DB'de fazla tablolar (modelde yok, bilinen haric): {len(extra_tables)}")
        for x in extra_tables[:40]:
            print(f"  + {x}")
        if len(extra_tables) > 40:
            print(f"  ... ve {len(extra_tables) - 40} diger")
    if missing_tables:
        print("EKSIK TABLOLAR (model var, DB yok):")
        for m in missing_tables:
            print(f"  - {m}")
    if column_issues:
        print("KOLON UYUSMAZLIKLARI:")
        for line in column_issues[:80]:
            print(line)
        if len(column_issues) > 80:
            print(f"  ... ve {len(column_issues) - 80} tablo daha")

    if nullability_issues:
        print("NULLABILITY UYUSMAZLIKLARI:")
        for line in nullability_issues[:80]:
            print(line)
        if len(nullability_issues) > 80:
            print(f"  ... ve {len(nullability_issues) - 80} tablo daha")

    if type_issues:
        print("TYPE UYUSMAZLIKLARI (yaklasik kontrol):")
        for line in type_issues[:80]:
            print(line)
        if len(type_issues) > 80:
            print(f"  ... ve {len(type_issues) - 80} tablo daha")

    if index_issues:
        print("INDEX UYUSMAZLIKLARI:")
        for line in index_issues[:80]:
            print(line)
        if len(index_issues) > 80:
            print(f"  ... ve {len(index_issues) - 80} tablo daha")

    if unique_issues:
        print("UNIQUE UYUSMAZLIKLARI:")
        for line in unique_issues[:80]:
            print(line)
        if len(unique_issues) > 80:
            print(f"  ... ve {len(unique_issues) - 80} tablo daha")

    if fk_issues:
        print("FK UYUSMAZLIKLARI:")
        for line in fk_issues[:80]:
            print(line)
        if len(fk_issues) > 80:
            print(f"  ... ve {len(fk_issues) - 80} tablo daha")

    has_issues = bool(
        missing_tables
        or column_issues
        or nullability_issues
        or type_issues
        or index_issues
        or unique_issues
        or fk_issues
    )

    if not has_issues:
        print("Sonuc: Sema (tablo/kolon/type/null/index/uq/fk) modellerle uyumlu (bilinen ekstra DB tablolar haric).")
        return 0
    print("Sonuc: Semada fark var; genelde `alembic upgrade head` veya eksik migration uygulanmali.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
