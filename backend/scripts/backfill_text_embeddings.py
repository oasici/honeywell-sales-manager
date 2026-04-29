"""V8 — backfill bigram-BoW sequence embeddings.

Walks every active opportunity and runs ``upsert_text_embedding``
for it. The result populates ``opportunity_text_embeddings`` so the
3-component / 4-component blend in
``deal_similarity_service.refresh_similarity_links`` actually has a
text vector to read; without this table populated, deal similarity
silently degrades to V7 (cosine + LCS) and "Benzer Fırsatlar" gives
weaker matches.

Idempotent: re-running upserts the same row per opp.

Usage:
    cd backend && source venv/bin/activate
    python -m scripts.backfill_text_embeddings --apply

Options:
    --apply         Actually run the upserts (default: dry-run only counts).
    --opp <ID>      Restrict to a specific opportunity (repeatable).
    --status <S>    Filter opps by status (default: "active").
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
)
logger = logging.getLogger("backfill_text_embeddings")


async def main_async(
    opportunity_ids: list[int] | None,
    status: str | None,
    apply: bool,
) -> None:
    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.opportunity import Opportunity
    from app.services.deal_similarity_service import upsert_text_embedding

    async with async_session() as db:
        if opportunity_ids:
            ids = list(opportunity_ids)
            logger.info("Targeting %d explicit opportunity ids", len(ids))
        else:
            stmt = select(Opportunity.id)
            if status:
                stmt = stmt.where(Opportunity.status == status)
            rows = (await db.execute(stmt)).scalars().all()
            ids = [int(r) for r in rows]
            logger.info(
                "Resolved %d opportunities (status=%s)",
                len(ids),
                status or "<any>",
            )

        if not apply:
            logger.info("DRY-RUN — would upsert text embeddings for %d opps.", len(ids))
            logger.info("Pass --apply to actually run.")
            return

        written = 0
        skipped = 0
        for i, opp_id in enumerate(ids, start=1):
            row = await upsert_text_embedding(db, opportunity_id=int(opp_id))
            if row is None:
                skipped += 1
            else:
                written += 1
            if i % 50 == 0:
                logger.info(
                    "Progress: %d/%d (written=%d, skipped=%d)",
                    i, len(ids), written, skipped,
                )
                # Periodic commit so a crash mid-run doesn't lose
                # everything — re-running is idempotent.
                await db.commit()

        await db.commit()
        logger.info(
            "Backfill complete: total=%d written=%d skipped=%d (skipped = no V6 token sequence yet)",
            len(ids), written, skipped,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill V8 BoW text embeddings.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually run the upserts (default: dry-run only).",
    )
    parser.add_argument(
        "--opp",
        action="append",
        type=int,
        default=None,
        help="Restrict to a specific opportunity id (repeatable).",
    )
    parser.add_argument(
        "--status",
        default="active",
        help="Filter opps by status (default: active). Pass empty string for any.",
    )
    args = parser.parse_args()
    asyncio.run(main_async(args.opp, args.status or None, args.apply))


if __name__ == "__main__":
    main()
