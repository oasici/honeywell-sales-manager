"""Manual RAG backfill — pumps existing CRM data into Qdrant.

Idempotent: re-running upserts the same points (vector_store builds
deterministic point IDs from entity ids).

Usage:
    cd backend && source venv/bin/activate
    FEATURE_RAG=true QDRANT_URL=http://qdrant:6333 \\
      python -m scripts.backfill_rag --apply

Options:
    --apply           Actually run (without it, just shows what would run)
    --since-hours N   Only index records changed in the last N hours
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
logger = logging.getLogger("backfill_rag")


async def main_async(since_hours: int | None) -> None:
    from app.core.config import settings
    from app.core.database import async_session
    from app.services.rag_backfill_service import run_full_backfill

    if not settings.FEATURE_RAG:
        logger.warning("FEATURE_RAG=false — set the flag and ensure QDRANT_URL is reachable.")
        return

    since = (
        datetime.now(timezone.utc) - timedelta(hours=since_hours)
        if since_hours is not None
        else None
    )

    async with async_session() as db:
        result = await run_full_backfill(db, since=since)

    logger.info(
        "Backfill complete: deals=%s interactions=%s competitors=%s",
        result.deals_indexed,
        result.interactions_indexed,
        result.competitors_indexed,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Qdrant RAG backfill")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--since-hours",
        type=int,
        default=None,
        help="Only index records updated within last N hours (default: full backfill)",
    )
    args = parser.parse_args()
    if not args.apply:
        logger.info(
            "Dry run — pass --apply. With --since-hours N, only the last "
            "N hours of changes are indexed."
        )
        return 0
    asyncio.run(main_async(args.since_hours))
    return 0


if __name__ == "__main__":
    sys.exit(main())
