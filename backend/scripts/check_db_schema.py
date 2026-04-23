#!/usr/bin/env python3
"""Karşılaştır: Alembic head, alembic_version ve SQLAlchemy model tabloları ↔ PostgreSQL public şeması.

Kullanım (repo kökünden veya backend içinden):
  DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/db' python3.11 scripts/check_db_schema.py

Çıkış kodu: 0 = uyumlu, 1 = eksik tablo/sütun veya Alembic geride.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# backend/ üst dizininde çalıştır
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.chdir(BACKEND)

import app.models  # noqa: F401 — tüm tabloları Base'e kaydet
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import Base


def _alembic_head_revision() -> str:
    cfg = Config(str(BACKEND / "alembic.ini"))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) != 1:
        raise RuntimeError(f"Beklenen tek Alembic head, bulunan: {heads}")
    return heads[0]


async def _run() -> int:
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        print("DATABASE_URL tanımlı değil.", file=sys.stderr)
        return 2

    engine = create_async_engine(url, echo=False)
    head = _alembic_head_revision()
    exit_code = 0

    async with engine.connect() as conn:

        def _db_table_names(c):
            insp = inspect(c)
            return set(insp.get_table_names(schema="public"))

        db_tables = await conn.run_sync(_db_table_names)

        # alembic_version
        ver_row = None
        if "alembic_version" in db_tables:
            r = await conn.execute(text("SELECT version_num FROM alembic_version"))
            ver_row = r.scalar_one_or_none()
        print(f"Alembic head (kod):     {head}")
        print(f"Alembic version (DB):  {ver_row or '(tablo yok / boş)'}")
        if ver_row != head:
            print("  → UYARI: Alembic revision DB ile head eşleşmiyor. `alembic upgrade head` gerekebilir.")
            exit_code = 1

        # Model tabloları (metadata'da kayıtlı)
        model_tables = sorted(
            t for t in Base.metadata.tables if not t.startswith("sqlite_")
        )
        missing_tables = [t for t in model_tables if t not in db_tables]
        if missing_tables:
            print(f"\nDB'de OLMAYAN model tabloları ({len(missing_tables)}):")
            for t in missing_tables[:80]:
                print(f"  - {t}")
            if len(missing_tables) > 80:
                print(f"  ... ve {len(missing_tables) - 80} tane daha")
            exit_code = 1
        else:
            print(f"\nModel tabloları DB'de mevcut: {len(model_tables)} tablo.")

        # Sütun farkları (ilk 40 tablo, yalnız eksik sütun)
        def _cols(c, table: str):
            insp = inspect(c)
            return {col["name"] for col in insp.get_columns(table, schema="public")}

        col_issues = 0
        for t in model_tables:
            if t not in db_tables:
                continue
            sa_cols = {c.name for c in Base.metadata.tables[t].columns}
            db_cols = await conn.run_sync(lambda c, tbl=t: _cols(c, tbl))
            missing_cols = sorted(sa_cols - db_cols)
            if missing_cols:
                print(f"\n  Tablo `{t}` — DB'de eksik sütunlar: {', '.join(missing_cols)}")
                col_issues += 1
                exit_code = 1
                if col_issues >= 25:
                    print("  ... (daha fazla tablo atlandı, çıkış kodu yine 1)")
                    break

        extra_in_db = sorted(db_tables - set(model_tables) - {"alembic_version"})
        if extra_in_db:
            print(f"\nDB'de olup modelde olmayan tablolar ({len(extra_in_db)}, bilgi):")
            for t in extra_in_db[:30]:
                print(f"  + {t}")
            if len(extra_in_db) > 30:
                print(f"  ... ve {len(extra_in_db) - 30} tane daha")

    await engine.dispose()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
