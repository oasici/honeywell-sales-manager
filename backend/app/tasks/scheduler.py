import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def poll_emails_task():
    """Background task: fetch new emails via Graph API delta query."""
    from app.core.database import async_session
    from app.services.graph_client import graph_client

    if not settings.AZURE_CLIENT_ID:
        return

    try:
        async with async_session() as db:
            from app.models.setting import Setting
            from sqlalchemy import select

            result = await db.execute(
                select(Setting).where(Setting.key == "graph_delta_link")
            )
            setting = result.scalar_one_or_none()
            delta_link = setting.value if setting else None

            emails, new_delta_link = await graph_client.fetch_new_emails(delta_link)

            if new_delta_link:
                if setting:
                    setting.value = new_delta_link
                else:
                    db.add(Setting(key="graph_delta_link", value=new_delta_link))
                await db.commit()

            logger.info(f"Polled {len(emails)} new emails via Graph API")

    except Exception as e:
        logger.error(f"Email polling failed: {e}")


async def check_expired_quotes_task():
    """Background task: mark expired quotes."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select, and_

    from app.core.database import async_session
    from app.models.quote import Quote

    try:
        async with async_session() as db:
            result = await db.execute(
                select(Quote).where(
                    and_(
                        Quote.status.in_(["draft", "approved", "sent"]),
                        Quote.created_at < datetime.now(timezone.utc) - timedelta(days=30),
                    )
                )
            )
            expired_quotes = result.scalars().all()
            for quote in expired_quotes:
                if quote.valid_days:
                    expiry = quote.created_at + timedelta(days=quote.valid_days)
                    if datetime.now(timezone.utc) > expiry:
                        quote.status = "expired"

            await db.commit()
            if expired_quotes:
                logger.info(f"Marked {len(expired_quotes)} quotes as expired")

    except Exception as e:
        logger.error(f"Quote expiry check failed: {e}")


def start_scheduler():
    """Start background scheduler with all tasks."""
    scheduler.add_job(
        poll_emails_task,
        "interval",
        minutes=settings.EMAIL_POLL_INTERVAL_MINUTES,
        id="email_poll",
        replace_existing=True,
    )
    scheduler.add_job(
        check_expired_quotes_task,
        "interval",
        hours=1,
        id="quote_expiry",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Background scheduler started")


def stop_scheduler():
    """Stop background scheduler."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Background scheduler stopped")
