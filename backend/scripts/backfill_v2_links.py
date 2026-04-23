"""
Sprint 0 — v2 Integration Hardening

Backfill script:
- existing emails -> opportunities (email_request.opportunity_id)
- existing quotes -> opportunities (quotes.opportunity_id)

Idempotent: safe to run multiple times.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy import select

from app.core.database import async_session
from app.models.email_request import EmailRequest
from app.models.quote import Quote
from app.services.opportunity_linking_service import ensure_opportunity_for_email


@dataclass
class BackfillStats:
    emails_scanned: int = 0
    emails_linked: int = 0
    quotes_scanned: int = 0
    quotes_linked: int = 0


async def _backfill_emails(*, dry_run: bool, limit: int | None) -> BackfillStats:
    stats = BackfillStats()
    async with async_session() as db:
        q = select(EmailRequest).where(EmailRequest.opportunity_id.is_(None))
        if limit:
            q = q.limit(limit)
        result = await db.execute(q)
        emails = result.scalars().all()
        stats.emails_scanned = len(emails)

        for email in emails:
            if not email.customer_id:
                # Can't link without customer. Leave for manual cleanup.
                continue
            opp_id = await ensure_opportunity_for_email(db, email=email, owner_hint=email.assigned_to)
            if email.opportunity_id != opp_id:
                stats.emails_linked += 1
                if not dry_run:
                    email.opportunity_id = opp_id

        if not dry_run:
            await db.commit()

    return stats


async def _backfill_quotes(*, dry_run: bool, limit: int | None) -> BackfillStats:
    stats = BackfillStats()
    async with async_session() as db:
        q = select(Quote).where(Quote.opportunity_id.is_(None))
        if limit:
            q = q.limit(limit)
        result = await db.execute(q)
        quotes = result.scalars().all()
        stats.quotes_scanned = len(quotes)

        # Strategy:
        # - If quote is from email_request, ensure email has opportunity and link quote to it
        # - Else: leave as-is for now (manual quotes need explicit linkage policy)
        for quote in quotes:
            if not quote.email_request_id:
                continue

            email = (
                await db.execute(select(EmailRequest).where(EmailRequest.id == quote.email_request_id))
            ).scalar_one_or_none()
            if not email or not email.customer_id:
                continue

            opp_id = await ensure_opportunity_for_email(db, email=email, owner_hint=quote.created_by or email.assigned_to)

            changed = False
            if email.opportunity_id != opp_id:
                changed = True
                if not dry_run:
                    email.opportunity_id = opp_id

            if quote.opportunity_id != opp_id:
                changed = True
                stats.quotes_linked += 1
                if not dry_run:
                    quote.opportunity_id = opp_id

            if changed and not dry_run:
                await db.flush()

        if not dry_run:
            await db.commit()

    return stats


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill v2 opportunity links for emails & quotes.")
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N rows per table")
    args = parser.parse_args()

    email_stats = await _backfill_emails(dry_run=args.dry_run, limit=args.limit)
    quote_stats = await _backfill_quotes(dry_run=args.dry_run, limit=args.limit)

    print("Backfill complete.")
    print(
        f"Emails scanned={email_stats.emails_scanned} linked={email_stats.emails_linked}"
    )
    print(
        f"Quotes scanned={quote_stats.quotes_scanned} linked={quote_stats.quotes_linked}"
    )
    if args.dry_run:
        print("Dry-run: no changes were written.")


if __name__ == "__main__":
    asyncio.run(main())

