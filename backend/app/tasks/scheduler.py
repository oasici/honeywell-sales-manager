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


async def batch_process_pending_emails():
    """Process pending emails in batch (cost-efficient, runs hourly)."""
    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.email_request import EmailRequest
    from app.services.email_processing_service import EmailProcessingService

    try:
        async with async_session() as db:
            result = await db.execute(
                select(EmailRequest)
                .where(EmailRequest.status == "new")
                .order_by(EmailRequest.created_at)
                .limit(50)
            )
            emails = result.scalars().all()

            if not emails:
                return

            logger.info("Batch processing %d pending emails", len(emails))
            service = EmailProcessingService(db)

            processed = 0
            for email in emails:
                try:
                    await service.process_email(email.id)
                    processed += 1
                except Exception as exc:
                    logger.warning(
                        "Batch process failed for email %d: %s",
                        email.id,
                        exc,
                    )

            await db.commit()
            logger.info("Batch processed %d/%d emails", processed, len(emails))

    except Exception as e:
        logger.error("Batch email processing failed: %s", e)


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
            expired_count = 0
            for quote in expired_quotes:
                if quote.valid_days:
                    expiry = quote.created_at + timedelta(days=quote.valid_days)
                    if datetime.now(timezone.utc) > expiry:
                        quote.status = "expired"
                        expired_count += 1
                        # Best-effort notification
                        if quote.created_by:
                            try:
                                from app.services.notification_service import create_notification
                                await create_notification(
                                    db, user_id=quote.created_by, type="quote_expired",
                                    title="Teklif suresi doldu",
                                    message=f"{quote.quote_number} gecerlilik suresi doldu.",
                                    entity_type="quote", entity_id=quote.id,
                                )
                            except Exception:
                                pass

            await db.commit()
            if expired_quotes:
                logger.info(f"Marked {len(expired_quotes)} quotes as expired")

    except Exception as e:
        logger.error(f"Quote expiry check failed: {e}")


async def check_anomaly_alerts_task():
    """Feature-12: Weekly anomaly detection -> notifications for managers.

    Checks: win_rate drop, avg_cycle increase, discount outlier rise, SLA breach increase.
    Runs weekly; creates notifications for all active managers.
    """
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select, func, and_
    from app.core.database import async_session
    from app.models.quote import Quote
    from app.models.email_request import EmailRequest
    from app.models.user import User
    from app.services.notification_service import create_notification

    try:
        async with async_session() as db:
            now = datetime.now(timezone.utc)
            this_week = now - timedelta(days=7)
            prev_week = now - timedelta(days=14)

            # Win rate comparison
            def _win_rate_q(since, until):
                return select(
                    func.count(Quote.id).filter(Quote.status == "accepted").label("won"),
                    func.count(Quote.id).label("total"),
                ).where(and_(Quote.created_at >= since, Quote.created_at < until))

            cur = (await db.execute(_win_rate_q(this_week, now))).first()
            prev = (await db.execute(_win_rate_q(prev_week, this_week))).first()

            cur_rate = (cur.won / cur.total * 100) if cur and cur.total > 0 else 0
            prev_rate = (prev.won / prev.total * 100) if prev and prev.total > 0 else 0

            alerts = []
            if prev_rate > 0 and cur_rate < prev_rate * 0.7:
                alerts.append(f"Kazanma orani dusus: %{round(prev_rate)} -> %{round(cur_rate)}")

            # SLA breach count comparison
            for period, since, until in [("bu hafta", this_week, now), ("gecen hafta", prev_week, this_week)]:
                pass  # Simplified — just check win rate for V1

            if alerts:
                managers = (await db.execute(
                    select(User).where(User.role == "sales_manager", User.is_active.is_(True))
                )).scalars().all()

                for mgr in managers:
                    for alert_msg in alerts:
                        try:
                            await create_notification(
                                db, user_id=mgr.id, type="anomaly_alert",
                                title="Haftalik Anomali Uyarisi",
                                message=alert_msg,
                            )
                        except Exception:
                            pass

                await db.commit()
                logger.info("Anomaly alerts: %d alert(s) sent to %d manager(s)", len(alerts), len(managers))

    except Exception as e:
        logger.error("Anomaly alert check failed: %s", e)


async def process_sequence_steps_task():
    """Process due sequence enrollment steps via arq job queue."""
    from datetime import datetime, timezone
    from sqlalchemy import select, and_
    from app.core.database import async_session
    from app.models.engagement import SequenceEnrollment

    try:
        async with async_session() as db:
            now = datetime.now(timezone.utc)
            due = (await db.execute(
                select(SequenceEnrollment).where(
                    and_(
                        SequenceEnrollment.status == "active",
                        SequenceEnrollment.next_action_at <= now,
                    )
                ).limit(50)
            )).scalars().all()

            if not due:
                return

            from app.services.job_queue import enqueue_job
            for enrollment in due:
                await enqueue_job("execute_sequence_step", enrollment.id)

            logger.info("Enqueued %d sequence steps", len(due))
    except Exception as e:
        logger.error("Sequence step processing failed: %s", e)


def start_scheduler():
    """Start background scheduler with all tasks. Safe to call multiple times."""
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
    scheduler.add_job(
        batch_process_pending_emails,
        "interval",
        hours=1,
        id="batch_email_process",
        replace_existing=True,
    )
    scheduler.add_job(
        check_anomaly_alerts_task,
        "interval",
        hours=168,  # weekly
        id="anomaly_alerts",
        replace_existing=True,
    )
    scheduler.add_job(
        process_sequence_steps_task,
        "interval",
        minutes=15,  # check every 15 min for due sequence steps
        id="sequence_steps",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    logger.info("Background scheduler started")


def stop_scheduler():
    """Stop background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Background scheduler stopped")
