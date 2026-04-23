"""
Sprint 0 — v2 Integration Hardening

Orphan opportunity cleanup:
- Delete opportunities that have *no* linked artifacts (quotes, emails, activities, tasks, signals, events).
- Supports dry-run and age cutoff to reduce risk.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, exists, select

from app.core.database import async_session
from app.models.activity_log import ActivityLog
from app.models.email_request import EmailRequest
from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal, Task
from app.models.quote import Quote


async def main() -> None:
    parser = argparse.ArgumentParser(description="Delete orphan opportunities (no artifacts).")
    parser.add_argument("--dry-run", action="store_true", help="Do not delete, only report count")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete rows. Without this, the script behaves like dry-run.",
    )
    parser.add_argument(
        "--older-than-days",
        type=int,
        default=14,
        help="Only consider opportunities created before N days ago",
    )
    parser.add_argument("--limit", type=int, default=None, help="Delete at most N opportunities")
    args = parser.parse_args()

    if args.older_than_days < 1:
        raise SystemExit("--older-than-days en az 1 olmali")

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.older_than_days)

    async with async_session() as db:
        base = select(Opportunity.id).where(Opportunity.created_at < cutoff)

        # Keep if any linked artifacts exist
        base = base.where(
            ~exists(select(1).where(Quote.opportunity_id == Opportunity.id)),
            ~exists(select(1).where(EmailRequest.opportunity_id == Opportunity.id)),
            ~exists(select(1).where(ActivityLog.opportunity_id == Opportunity.id)),
            ~exists(select(1).where(Task.opportunity_id == Opportunity.id)),
            ~exists(select(1).where(OpportunitySignal.opportunity_id == Opportunity.id)),
            ~exists(select(1).where(OpportunityEvent.opportunity_id == Opportunity.id)),
        )

        if args.limit:
            base = base.limit(args.limit)

        ids = [row[0] for row in (await db.execute(base)).all()]
        if not ids:
            print("No orphan opportunities found.")
            return

        print(f"Found {len(ids)} orphan opportunities (older than {args.older_than_days} days).")
        print("Sample IDs:", ids[: min(20, len(ids))])

        if args.dry_run or not args.execute:
            print("Dry-run: no deletions performed. Pass --execute to delete.")
            return

        await db.execute(delete(Opportunity).where(Opportunity.id.in_(ids)))
        await db.commit()
        print(f"Deleted {len(ids)} orphan opportunities.")


if __name__ == "__main__":
    asyncio.run(main())

