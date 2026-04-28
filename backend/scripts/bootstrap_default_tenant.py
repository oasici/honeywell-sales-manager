"""Bootstrap the default tenant + backfill NULL ``tenant_id`` rows.

The V8 migration (``20260427_v8_crm_tenant_id``) adds a nullable
``tenant_id`` column to users/customers/opportunities/quotes/leads.
Existing single-tenant deployments stay on NULLs and downstream
``scoped_for_user`` calls become no-ops — that's intentional, the
schema change is forward-compatible.

When an operator wants to flip a deployment into multi-tenant mode
they run this script. It:

1. Creates (or reuses) a Tenant row with the supplied ``--name``.
2. Updates every NULL ``tenant_id`` row across the 5 CRM core tables
   to point at that tenant.

The script is **idempotent** — safe to re-run; subsequent runs are
no-ops because the targeted rows already have a ``tenant_id``.

Usage:
    cd backend && source venv/bin/activate
    python -m scripts.bootstrap_default_tenant --name "Honeywell TR" --apply

Options:
    --name <STR>     Tenant name (unique); reused if it already exists.
    --region <STR>   Optional region label stored on the Tenant row.
    --plan-tier <S>  Tenant plan tier (default: "standard").
    --apply          Actually run the UPDATEs (default: dry-run).

The dry-run prints the exact UPDATE statements it would issue plus
the row counts, so you can review before flipping production.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
logger = logging.getLogger("bootstrap_default_tenant")


_CORE_TABLES = ("users", "customers", "opportunities", "quotes", "leads")


async def _count_null_tenant(db, table: str) -> int:
    from sqlalchemy import text

    result = await db.execute(
        text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id IS NULL")
    )
    return int(result.scalar() or 0)


async def _backfill_table(db, table: str, tenant_id: int) -> int:
    from sqlalchemy import text

    result = await db.execute(
        text(f"UPDATE {table} SET tenant_id = :tid WHERE tenant_id IS NULL"),
        {"tid": tenant_id},
    )
    return int(result.rowcount or 0)


async def main_async(name: str, region: str | None, plan_tier: str, apply: bool) -> None:
    from app.core.database import async_session
    from app.services.tenant_context import ensure_tenant

    async with async_session() as db:
        # In dry-run mode we still need to *resolve* the tenant id to
        # report what the apply phase would target — but we MUST roll
        # back so we don't leave an orphan ``tenants`` row when the
        # operator later runs the apply phase (that path calls
        # ``ensure_tenant`` again and would otherwise create a second
        # row with the same name + a fresh id, leaking a duplicate).
        tenant = await ensure_tenant(
            db, name=name, region=region, plan_tier=plan_tier
        )
        await db.flush()
        tenant_id = int(tenant.id)
        logger.info("Tenant resolved: id=%s name=%r", tenant_id, name)

        # Dry-run summary first so the operator can review.
        for table in _CORE_TABLES:
            null_count = await _count_null_tenant(db, table)
            logger.info("  %-15s NULL tenant_id rows: %d", table, null_count)

        if not apply:
            # Roll back so the resolved tenant row doesn't persist.
            # ``ensure_tenant`` is idempotent against a real (committed)
            # tenant on the next apply call — but if we'd left an
            # un-committed row from this session, async_session's
            # auto-commit-on-close in some configs would persist it
            # and then the apply call would create a SECOND row.
            await db.rollback()
            logger.info("DRY-RUN — pass --apply to actually run the UPDATEs.")
            return

        total = 0
        for table in _CORE_TABLES:
            updated = await _backfill_table(db, table, tenant_id)
            logger.info("  %-15s updated: %d", table, updated)
            total += updated

        await db.commit()
        logger.info("Backfilled %d rows into tenant_id=%s.", total, tenant_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap the default tenant.")
    parser.add_argument("--name", required=True, help="Tenant display name")
    parser.add_argument("--region", default=None, help="Optional region label")
    parser.add_argument("--plan-tier", default="standard", help="Plan tier label")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually run the backfill (default: dry-run)",
    )
    args = parser.parse_args()

    asyncio.run(
        main_async(
            name=args.name,
            region=args.region,
            plan_tier=args.plan_tier,
            apply=args.apply,
        )
    )


if __name__ == "__main__":
    main()
