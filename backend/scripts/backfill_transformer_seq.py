"""V12 — backfill transformer sequence embeddings for existing deals.

Idempotent: re-running upserts the same row per opportunity. Safe to
schedule nightly while the feature is rolling out.

Usage:
    cd backend && source venv/bin/activate
    FEATURE_TRANSFORMER_SEQ_EMBEDDING=true \\
      python -m scripts.backfill_transformer_seq --apply

Options:
    --apply         Actually run (without it, just shows the plan).
    --opp <ID>      Restrict to one opportunity id (repeatable).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
logger = logging.getLogger("backfill_transformer_seq")


async def main_async(opportunity_ids: list[int] | None, apply: bool) -> None:
    from app.core.config import settings
    from app.core.database import async_session
    from app.services.transformer_seq_repository import (
        backfill_transformer_seq_embeddings,
    )

    if not settings.FEATURE_TRANSFORMER_SEQ_EMBEDDING:
        logger.warning(
            "FEATURE_TRANSFORMER_SEQ_EMBEDDING=false — set the flag before running."
        )
        return

    if not apply:
        logger.info(
            "DRY-RUN — would encode %s. Pass --apply to actually backfill.",
            f"opps={opportunity_ids}" if opportunity_ids else "ALL deal embeddings",
        )
        return

    async with async_session() as db:
        stats = await backfill_transformer_seq_embeddings(
            db, opportunity_ids=opportunity_ids
        )
        await db.commit()
    logger.info(
        "processed=%d written=%d skipped=%d",
        stats["processed"],
        stats["written"],
        stats["skipped"],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill V12 transformer embeddings.")
    parser.add_argument(
        "--apply", action="store_true", help="Actually run the backfill."
    )
    parser.add_argument(
        "--opp",
        action="append",
        type=int,
        default=None,
        help="Restrict to a specific opportunity id (repeatable).",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.opp, args.apply))


if __name__ == "__main__":
    main()
