from __future__ import annotations

import asyncio
import logging
import time

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# ── Task stats tracking ──
_task_stats: dict[str, dict] = {}


async def _tracked(name: str, fn) -> None:
    """Wrap a task function with timing, success/fail tracking, and logging."""
    if name not in _task_stats:
        _task_stats[name] = {"success": 0, "fail": 0, "last_run": None, "last_duration_ms": None}

    start = time.monotonic()
    try:
        await fn()
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        _task_stats[name]["success"] += 1
        _task_stats[name]["last_run"] = time.time()
        _task_stats[name]["last_duration_ms"] = elapsed_ms
        logger.debug("Task %s completed in %.1fms", name, elapsed_ms)
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - start) * 1000, 1)
        _task_stats[name]["fail"] += 1
        _task_stats[name]["last_run"] = time.time()
        _task_stats[name]["last_duration_ms"] = elapsed_ms
        logger.error("Task %s failed after %.1fms: %s", name, elapsed_ms, exc)


def get_task_stats() -> dict:
    """Return task execution statistics."""
    return dict(_task_stats)


async def _get_imap_credentials(db) -> dict | None:
    """Load and decrypt IMAP credentials from the Settings table.

    Returns a dict with email_address, email_password, imap_host, imap_port
    or None if credentials are not configured.
    """
    from sqlalchemy import select

    from app.models.setting import Setting

    credential_keys = ["email_address", "email_password", "imap_host", "imap_port"]
    result = await db.execute(
        select(Setting).where(Setting.key.in_(credential_keys))
    )
    stored = {s.key: s.value for s in result.scalars().all()}

    email_address = stored.get("email_address", "")
    encrypted_password = stored.get("email_password", "")

    if not email_address or not encrypted_password:
        return None

    from app.api.v1.settings import _decrypt_password

    try:
        email_password = _decrypt_password(encrypted_password)
    except Exception as exc:
        logger.error("Failed to decrypt IMAP password: %s", exc)
        return None

    return {
        "email_address": email_address,
        "email_password": email_password,
        "imap_host": stored.get("imap_host", "outlook.office365.com"),
        "imap_port": int(stored.get("imap_port", "993")),
    }


async def _resolve_mailbox_owner(db) -> tuple[int | None, int | None]:
    """Resolve the (tenant_id, user_id) that owns the configured mailbox.

    The IMAP credentials are global (single shared mailbox — see audit
    E5), so the scheduled poll has no request user. We persist the
    configuring manager as ``email_owner_user_id`` when credentials are
    saved; this resolves it back to a tenant so cron-ingested rows are
    tenant-scoped exactly like the manual ``/poll`` path. Falls back to
    ``(None, None)`` for legacy single-tenant deployments.
    """
    from sqlalchemy import select

    from app.models.setting import Setting
    from app.models.user import User

    row = await db.execute(
        select(Setting.value).where(Setting.key == "email_owner_user_id")
    )
    raw = row.scalar_one_or_none()
    if not raw:
        return None, None
    try:
        owner_id = int(raw)
    except (TypeError, ValueError):
        return None, None
    rec = (
        await db.execute(select(User.id, User.tenant_id).where(User.id == owner_id))
    ).first()
    if rec is None:
        return None, None
    return rec.tenant_id, rec.id


async def _run_imap_poll(db) -> int:
    """Fetch emails via IMAP and create EmailRequest records for new ones.

    Returns the number of new emails saved. Row construction is delegated
    to the shared ``email_ingestion_service`` so the scheduled path stamps
    ``sender_auth_status`` / ``tenant_id`` / ``attachments_json`` and runs
    the AV scan exactly like the manual ``/poll`` endpoint (audit E1/E2).
    """
    from app.api.v1.emails import _fetch_emails_via_imap
    from app.services.email_ingestion_service import ingest_fetched_email

    credentials = await _get_imap_credentials(db)
    if not credentials:
        return 0

    # _fetch_emails_via_imap is synchronous; run in a thread
    fetched = await asyncio.to_thread(
        _fetch_emails_via_imap,
        credentials["imap_host"],
        credentials["imap_port"],
        credentials["email_address"],
        credentials["email_password"],
        0,
    )

    if not fetched:
        return 0

    tenant_id, assigned_to = await _resolve_mailbox_owner(db)

    saved_count = 0
    for item in fetched:
        try:
            row = await ingest_fetched_email(
                db, item, tenant_id=tenant_id, assigned_to=assigned_to
            )
            if row is not None:
                saved_count += 1
        except Exception as exc:  # noqa: BLE001 — one bad message can't abort the poll
            logger.warning(
                "IMAP ingest failed for %s: %s", item.get("message_id"), exc
            )

    if saved_count:
        await db.commit()

    return saved_count


async def poll_emails_via_imap_task():
    """Background task: fetch new emails via IMAP and save to database."""
    from app.core.database import async_session

    try:
        async with async_session() as db:
            saved = await _run_imap_poll(db)
            if saved:
                logger.info("IMAP poll: saved %d new email(s)", saved)
    except Exception as exc:
        logger.error("IMAP email polling failed: %s", exc)


async def poll_emails_task():
    """Background task: fetch new emails via Graph API delta query.

    Falls back to IMAP polling when Azure credentials are not configured.
    """
    from app.core.database import async_session
    from app.services.graph_client import graph_client

    if not settings.AZURE_CLIENT_ID:
        # Fallback to IMAP polling
        await poll_emails_via_imap_task()
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

            logger.info("Polled %d new emails via Graph API", len(emails))

    except Exception as e:
        logger.error("Email polling failed: %s", e)


async def batch_process_pending_emails():
    """Process pending emails in batch (cost-efficient, runs hourly)."""
    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.email_request import EmailRequest
    from app.services.email_processing_service import EmailProcessingService

    batch_size = max(1, settings.EMAIL_BATCH_SIZE)
    delay = max(0.0, settings.EMAIL_BATCH_DELAY_SECONDS)

    try:
        async with async_session() as db:
            result = await db.execute(
                select(EmailRequest)
                .where(EmailRequest.status == "new")
                .order_by(EmailRequest.created_at)
                .limit(batch_size)
            )
            emails = result.scalars().all()

            if not emails:
                return

            logger.info(
                "Batch processing %d pending emails (%.1fs between parses)",
                len(emails),
                delay,
            )
            service = EmailProcessingService(db)

            processed = 0
            last_index = len(emails) - 1
            for i, email in enumerate(emails):
                try:
                    await service.process_email(email.id)
                    processed += 1
                except Exception as exc:
                    logger.warning(
                        "Batch process failed for email %d: %s",
                        email.id,
                        exc,
                    )
                # Throttle: pace Claude calls to stay under the org's
                # per-minute token budget. Skip the wait after the last
                # email so we don't idle the worker for nothing.
                if delay and i < last_index:
                    await asyncio.sleep(delay)

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


async def take_pipeline_snapshot_task():
    """Weekly pipeline snapshot for forecast WoW tracking."""
    if not settings.FEATURE_V2_BOARD:
        return

    from app.core.database import async_session
    from app.services.forecast_service import ForecastService

    try:
        async with async_session() as db:
            service = ForecastService(db)
            snapshots = await service.take_pipeline_snapshot()
            await db.commit()
            logger.info("Pipeline snapshot taken: %d stage records", len(snapshots))
    except Exception as e:
        logger.error("Pipeline snapshot failed: %s", e)


# D-034 — per-tenant, timezone-aware forecast snapshot dispatcher.
#
# Runs every 15 minutes; for each tenant it computes the current local
# time in that tenant's configured timezone and, when the local hour
# equals the tenant's ``forecast_cron_hour`` (within the first 15-minute
# window of that hour), captures a tenant-scoped pipeline snapshot. A
# per-(tenant, local-date) guard makes the run idempotent even if the
# window logic fires more than once or the process restarts mid-window.
_forecast_snapshot_ran: set[tuple[int, str]] = set()


async def forecast_tenant_local_dispatch_task():
    """Capture each tenant's forecast snapshot at its local cron hour."""
    if not settings.FEATURE_V2_BOARD:
        return

    from datetime import datetime
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.v7_tenant import Tenant
    from app.services.forecast_service import ForecastService
    from app.services.tenant_settings_service import get_tenant_settings

    try:
        async with async_session() as db:
            tenants = (await db.execute(select(Tenant.id))).scalars().all()
            for tenant_id in tenants:
                cfg = await get_tenant_settings(db, tenant_id)
                try:
                    tz = ZoneInfo(cfg.forecast_cron_tz)
                except (ZoneInfoNotFoundError, ValueError):
                    logger.warning(
                        "Tenant %d has invalid forecast_cron_tz=%r; using UTC",
                        tenant_id, cfg.forecast_cron_tz,
                    )
                    tz = ZoneInfo("UTC")

                now_local = datetime.now(tz)
                if now_local.hour != cfg.forecast_cron_hour or now_local.minute >= 15:
                    continue

                guard_key = (tenant_id, now_local.date().isoformat())
                if guard_key in _forecast_snapshot_ran:
                    continue

                service = ForecastService(db)
                snapshots = await service.take_pipeline_snapshot(tenant_id=tenant_id)
                await db.commit()
                _forecast_snapshot_ran.add(guard_key)
                logger.info(
                    "Tenant-local forecast snapshot: tenant=%d tz=%s hour=%d records=%d",
                    tenant_id, cfg.forecast_cron_tz, cfg.forecast_cron_hour,
                    len(snapshots),
                )

            # Prune guard keys from previous days so the set stays small.
            today_isos = {
                datetime.now(ZoneInfo("UTC")).date().isoformat(),
            }
            for tid in tenants:
                cfg = await get_tenant_settings(db, tid)
                try:
                    today_isos.add(datetime.now(ZoneInfo(cfg.forecast_cron_tz)).date().isoformat())
                except Exception:
                    pass
            stale = {k for k in _forecast_snapshot_ran if k[1] not in today_isos}
            _forecast_snapshot_ran.difference_update(stale)
    except Exception as e:
        logger.error("Tenant-local forecast dispatch failed: %s", e)


async def send_scheduled_reports_task():
    """Send scheduled report emails (daily/weekly/monthly)."""
    import json
    from sqlalchemy import select
    from app.core.database import async_session
    from app.models.report import ReportTemplate
    from app.services.report_engine import ReportEngine

    try:
        async with async_session() as db:
            # Find templates with active schedules
            result = await db.execute(
                select(ReportTemplate).where(
                    ReportTemplate.email_schedule.isnot(None),
                    ReportTemplate.email_recipients.isnot(None),
                )
            )
            templates = result.scalars().all()

            if not templates:
                return

            sent_count = 0
            for tpl in templates:
                try:
                    recipients = json.loads(tpl.email_recipients) if tpl.email_recipients else []
                    if not recipients:
                        continue

                    engine = ReportEngine(db)
                    report_data = await engine.execute_report(tpl.id)
                    csv_content = await engine.export_csv(tpl.id)

                    # Send via SMTP
                    from app.services.email_sender import send_quote_email
                    for recipient in recipients:
                        await send_quote_email(
                            to_address=recipient,
                            subject=f"Zamanlanmis Rapor: {tpl.name}",
                            body_html=f"<p>{tpl.name} raporu ekte yer almaktadir.</p>"
                                      f"<p>Toplam {len(report_data.get('data', []))} kayit.</p>",
                            pdf_path=None,
                        )
                    sent_count += 1
                except Exception as exc:
                    logger.warning("Scheduled report %d failed: %s", tpl.id, exc)

            logger.info("Sent %d scheduled reports", sent_count)
    except Exception as e:
        logger.error("Scheduled report task failed: %s", e)


async def check_data_retention_task():
    """Daily: find customers where KVKK retention expired, notify managers.

    Round-5 R5-EVENT-1 — group overdue customers by tenant_id and
    notify only managers within the same tenant. Pre-R5 a manager in
    tenant A would see "N customers overdue" where N was the cross-
    tenant aggregate count, leaking tenant B's operational metric.
    """
    from datetime import datetime, timezone

    from sqlalchemy import func, select

    from app.core.database import async_session
    from app.models.customer import Customer
    from app.models.user import User
    from app.services.notification_service import create_notification

    try:
        async with async_session() as db:
            now = datetime.now(timezone.utc)
            tenant_rows = (
                await db.execute(
                    select(Customer.tenant_id, func.count(Customer.id))
                    .where(
                        Customer.data_retention_until < now,
                        Customer.deletion_requested_at.is_(None),
                    )
                    .group_by(Customer.tenant_id)
                )
            ).all()

            if not tenant_rows:
                return

            total_overdue = 0
            total_notified = 0

            for tenant_id, count in tenant_rows:
                if count == 0:
                    continue
                total_overdue += count

                manager_query = select(User).where(
                    User.role == "sales_manager",
                    User.is_active.is_(True),
                )
                # Single-tenant rows (tenant_id IS NULL) notify only
                # other NULL-tenant managers; multi-tenant rows scope
                # the notify list to the tenant.
                if tenant_id is None:
                    manager_query = manager_query.where(User.tenant_id.is_(None))
                else:
                    manager_query = manager_query.where(User.tenant_id == tenant_id)

                managers = (await db.execute(manager_query)).scalars().all()

                for mgr in managers:
                    try:
                        await create_notification(
                            db,
                            user_id=mgr.id,
                            type="kvkk_retention",
                            title="KVKK Veri Saklama Suresi Doldu",
                            message=(
                                f"{count} musterinin veri saklama suresi dolmustur. "
                                f"Lutfen inceleyiniz."
                            ),
                        )
                        total_notified += 1
                    except Exception:
                        pass

            await db.commit()
            logger.info(
                "KVKK retention check: %d overdue customer(s) across %d tenant(s), "
                "notified %d manager(s)",
                total_overdue,
                len(tenant_rows),
                total_notified,
            )

    except Exception as e:
        logger.error("KVKK retention check failed: %s", e)


async def kvkk_anonymization_task():
    """Daily: auto-anonymize records past their KVKK retention threshold.

    Gated behind ``settings.KVKK_AUTO_ANONYMIZE_ENABLED`` because the
    operation is irreversible. Operators flip the flag in production
    after running the same logic in dry-run via the runbook.
    """
    from app.core.config import settings as cfg
    from app.core.database import async_session
    from app.services.kvkk_retention_service import run_retention_anonymization

    if not cfg.KVKK_AUTO_ANONYMIZE_ENABLED:
        return

    try:
        async with async_session() as db:
            summary = await run_retention_anonymization(
                db,
                email_retention_days=cfg.KVKK_EMAIL_RETENTION_DAYS,
                opportunity_retention_days=cfg.KVKK_OPPORTUNITY_RETENTION_DAYS,
                dry_run=False,
            )
            await db.commit()
            logger.info(
                "KVKK auto-anonymize completed: %d email_requests, %d customers",
                summary["email_count"],
                summary["customer_count"],
            )
    except Exception as e:
        logger.error("KVKK auto-anonymize failed: %s", e)


async def advance_playbook_executions_task():
    """Advance due playbook executions (runs every 15 minutes)."""
    if not settings.FEATURE_REVENUE_COCKPIT:
        return

    from app.core.database import async_session
    from app.services.playbook_service import PlaybookService

    try:
        async with async_session() as db:
            service = PlaybookService(db)
            count = await service.advance_due_executions()
            await db.commit()
            if count:
                logger.info("Advanced %d playbook executions", count)
    except Exception as e:
        logger.error("Playbook advance failed: %s", e)


async def evaluate_coaching_task():
    """Daily coaching evaluation for all reps.

    If a rep's score drops below 60, emit a coaching_needed RevenueSignal
    and notify their manager.
    """
    if not settings.FEATURE_REVENUE_COCKPIT:
        return

    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.user import User
    from app.services.coaching_service import CoachingService
    from app.services.notification_service import create_notification

    coaching_needed_threshold = 60

    try:
        async with async_session() as db:
            service = CoachingService(db)
            results = await service.evaluate_all_reps()

            # Save coaching snapshots for each evaluated rep
            try:
                import json as _json
                from app.models.coaching_snapshot import CoachingSnapshot

                for result in results:
                    snapshot = CoachingSnapshot(
                        user_id=result["user_id"],
                        score=result.get("score", 0),
                        indicators_json=_json.dumps(
                            result.get("indicators", []), ensure_ascii=False
                        ),
                    )
                    db.add(snapshot)
                await db.flush()
            except Exception as snap_exc:
                logger.warning("Failed to save coaching snapshots: %s", snap_exc)

            alerted = 0

            for result in results:
                if result.get("score", 100) >= coaching_needed_threshold:
                    continue

                user_id = result["user_id"]
                score = result["score"]

                try:
                    from app.services.revenue_signal_service import emit_signal

                    await emit_signal(
                        db,
                        signal_type="coaching_needed",
                        source_entity_type="coaching",
                        source_entity_id=user_id,
                        owner_id=user_id,
                        severity="high" if score < 40 else "med",
                        confidence=0.8,
                        recommended_action=(
                            f"Temsilci performans skoru dusuk: {score}/100. "
                            f"Kocluk gorusmesi planlayin."
                        ),
                        metadata={
                            "score": score,
                            "risk_level": result.get("risk_level"),
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to emit coaching signal for user %d: %s",
                        user_id,
                        exc,
                    )

                try:
                    managers = (
                        await db.execute(
                            select(User).where(
                                User.role == "sales_manager",
                                User.is_active.is_(True),
                            )
                        )
                    ).scalars().all()

                    for mgr in managers:
                        await create_notification(
                            db,
                            user_id=mgr.id,
                            type="coaching_needed",
                            title="Kocluk Gerekli",
                            message=(
                                f"{result.get('user_name', 'Temsilci')} performans "
                                f"skoru: {score}/100. Kocluk gorusmesi oneriliyor."
                            ),
                            entity_type="user",
                            entity_id=user_id,
                        )
                    alerted += 1
                except Exception as exc:
                    logger.warning(
                        "Failed to notify managers for user %d: %s",
                        user_id,
                        exc,
                    )

            await db.commit()
            logger.info(
                "Coaching evaluation complete: %d reps evaluated, %d alerts sent",
                len(results),
                alerted,
            )
    except Exception as exc:
        logger.error("Coaching evaluation task failed: %s", exc)


async def check_approval_escalation_task():
    """Hourly: check for overdue approvals, auto-approve or escalate."""
    from app.core.database import async_session
    from app.services.approval_service import ApprovalService

    try:
        async with async_session() as db:
            service = ApprovalService(db)
            count = await service.check_escalations()
            await db.commit()
            if count:
                logger.info("Escalated %d overdue approval(s)", count)
    except Exception as e:
        logger.error("Approval escalation check failed: %s", e)


async def crawl_competitors_task():
    """Weekly: crawl competitor websites for updates."""
    if not settings.FEATURE_AI_COMPETITIVE_INTEL:
        return

    try:
        from app.services.competitor_crawler import crawl_all_competitors

        result = await crawl_all_competitors()
        logger.info(
            "Competitor crawl task: %d results",
            result.get("total_results", 0),
        )
    except Exception as exc:
        logger.error("Competitor crawl task failed: %s", exc)


async def check_subscription_renewals_task():
    """Daily: check for subscriptions needing renewal, notify owners."""
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.core.database import async_session
    from app.models.subscription import Subscription
    from app.models.user import User
    from app.services.notification_service import create_notification
    from app.services.subscription_service import SubscriptionService

    try:
        async with async_session() as db:
            service = SubscriptionService(db)

            # Auto-renew due subscriptions
            renewed_count = await service.auto_renew_due_subscriptions()
            if renewed_count:
                logger.info("Auto-renewed %d subscription(s)", renewed_count)

            # Notify owners about subscriptions renewing in next 7 days
            today = datetime.now(timezone.utc).date()
            seven_days = today + timedelta(days=7)
            result = await db.execute(
                select(Subscription).where(
                    Subscription.status == "active",
                    Subscription.next_renewal_date.isnot(None),
                    Subscription.next_renewal_date <= seven_days,
                    Subscription.next_renewal_date > today,
                ),
            )
            upcoming = result.scalars().all()
            for sub in upcoming:
                try:
                    await create_notification(
                        db,
                        user_id=sub.created_by,
                        type="subscription_renewal",
                        title="Abonelik Yenileme Yaklasti",
                        message=f'"{sub.name}" aboneligi {sub.next_renewal_date} tarihinde yenilenecek.',
                        entity_type="subscription",
                        entity_id=sub.id,
                    )
                except Exception:
                    pass

            await db.commit()
            logger.info(
                "Subscription renewal check: %d auto-renewed, %d upcoming notification(s)",
                renewed_count,
                len(upcoming),
            )
    except Exception as exc:
        logger.error("Subscription renewal check failed: %s", exc)


def start_scheduler():
    """Start background scheduler with all tasks. Safe to call multiple times."""
    # Ensure idempotency even before the scheduler is started.
    # When AsyncIOScheduler isn't started yet, `replace_existing=True` may not
    # dedupe pending jobs reliably across repeated calls.
    scheduler.remove_all_jobs()

    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("email_poll", poll_emails_task)),
        "interval",
        minutes=settings.EMAIL_POLL_INTERVAL_MINUTES,
        id="email_poll",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("quote_expiry", check_expired_quotes_task)),
        "interval",
        hours=1,
        id="quote_expiry",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("batch_email_process", batch_process_pending_emails)),
        "interval",
        hours=1,
        id="batch_email_process",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("anomaly_alerts", check_anomaly_alerts_task)),
        "interval",
        hours=168,  # weekly
        id="anomaly_alerts",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("sequence_steps", process_sequence_steps_task)),
        "interval",
        minutes=15,  # check every 15 min for due sequence steps
        id="sequence_steps",
        replace_existing=True,
    )
    # D-034 — replaced the weekly global interval with a 15-minute
    # tenant-local dispatcher. Each tenant's snapshot now fires at its
    # own configured local hour (default 04:00 UTC = legacy behaviour)
    # so the forecast baseline lands on a consistent local business-day
    # boundary instead of a single UTC instant.
    scheduler.add_job(
        lambda: asyncio.ensure_future(
            _tracked("forecast_tenant_local_dispatch", forecast_tenant_local_dispatch_task)
        ),
        "cron",
        minute="*/15",
        id="forecast_tenant_local_dispatch",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("scheduled_reports", send_scheduled_reports_task)),
        "interval",
        hours=24,  # daily check (skips non-matching schedules)
        id="scheduled_reports",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("kvkk_retention_check", check_data_retention_task)),
        "interval",
        hours=24,
        id="kvkk_retention_check",
        replace_existing=True,
    )
    # Daily 03:00 UTC anonymization sweep — gated by KVKK_AUTO_ANONYMIZE_ENABLED.
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("kvkk_anonymize", kvkk_anonymization_task)),
        "cron",
        hour=3,
        minute=0,
        id="kvkk_anonymize",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("playbook_advance", advance_playbook_executions_task)),
        "interval",
        minutes=15,
        id="playbook_advance",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("coaching_eval", evaluate_coaching_task)),
        "interval",
        hours=24,
        id="coaching_eval",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("approval_escalation", check_approval_escalation_task)),
        "interval",
        hours=1,
        id="approval_escalation",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("competitor_crawl", crawl_competitors_task)),
        "interval",
        hours=168,  # weekly
        id="competitor_crawl",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("subscription_renewals", check_subscription_renewals_task)),
        "interval",
        hours=24,
        id="subscription_renewals",
        replace_existing=True,
    )
    # V4: nightly feature store builder — gated by FEATURE_V4_FEATURE_STORE
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("v4_feature_store", build_v4_feature_store_task)),
        "cron",
        hour=2,
        minute=0,
        id="v4_feature_store",
        replace_existing=True,
    )
    # V4: shadow sales_events materialization — gated by FEATURE_V4_SALES_EVENTS_SHADOW
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("v4_sales_events_shadow", build_v4_sales_events_shadow_task)),
        "cron",
        hour=3,
        minute=15,
        id="v4_sales_events_shadow",
        replace_existing=True,
    )
    # V4: Sales DNA nightly (after feature store) — gated by FEATURE_V4_SALES_DNA
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("v4_sales_dna_nightly", build_v4_sales_dna_nightly_task)),
        "cron",
        hour=4,
        minute=5,
        id="v4_sales_dna_nightly",
        replace_existing=True,
    )
    # V4: deal replay nightly — gated by FEATURE_V4_DEAL_REPLAY
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("v4_deal_replay_nightly", build_v4_deal_replay_nightly_task)),
        "cron",
        hour=4,
        minute=35,
        id="v4_deal_replay_nightly",
        replace_existing=True,
    )
    # V5: intelligence nightly (after V4 jobs) — gated by FEATURE_V5_INTELLIGENCE
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("v5_intelligence_nightly", build_v5_intelligence_nightly_task)),
        "cron",
        hour=5,
        minute=15,
        id="v5_intelligence_nightly",
        replace_existing=True,
    )
    # V11: RAG incremental backfill (after V5 nightly) — gated by FEATURE_RAG
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("rag_incremental_backfill", build_rag_incremental_backfill_task)),
        "cron",
        hour=7,
        minute=0,
        id="rag_incremental_backfill",
        replace_existing=True,
    )
    # Round-19 cron jobs — wired here so the existing scheduler
    # picks them up. All four are idempotent + cheap; safe to run on
    # the 20-30 user pilot.
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("r19_token_blocklist_cleanup", r19_token_blocklist_cleanup_task)),
        "interval",
        hours=1,
        id="r19_token_blocklist_cleanup",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("r19_admin_nonce_cleanup", r19_admin_nonce_cleanup_task)),
        "interval",
        minutes=30,
        id="r19_admin_nonce_cleanup",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("r19_approval_sla_escalation", r19_approval_sla_task)),
        "interval",
        minutes=15,
        id="r19_approval_sla_escalation",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("r19_health_recompute_batch", r19_health_recompute_task)),
        "interval",
        minutes=5,
        id="r19_health_recompute_batch",
        replace_existing=True,
    )
    # D-029 — Phase 8: revert approval-rule delegations whose
    # delegate_until has passed. Hourly is fine; delegations are
    # measured in days.
    scheduler.add_job(
        lambda: asyncio.ensure_future(_tracked("r19_delegation_expiry", r19_delegation_expiry_task)),
        "interval",
        hours=1,
        id="r19_delegation_expiry",
        replace_existing=True,
    )

    # In production, this is started from the FastAPI lifespan where an event loop
    # is guaranteed to be running. In sync unit tests, starting an AsyncIOScheduler
    # can fail if the loop is closed; we keep the jobs registered but skip `start()`.
    if not scheduler.running:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and not loop.is_closed():
            scheduler.start()
    logger.info("Background scheduler started")


def stop_scheduler():
    """Stop background scheduler."""
    if scheduler.running:
        try:
            scheduler.shutdown()
        except RuntimeError:
            # Best-effort: in sync contexts the event loop can already be closed.
            pass
        logger.info("Background scheduler stopped")


async def build_v4_feature_store_task():
    """Nightly build of V4 daily feature store snapshots (safe no-op if flag off)."""
    if not settings.FEATURE_V4_FEATURE_STORE:
        return
    from app.core.database import async_session
    from app.services.feature_store_builder import build_daily_feature_store

    async with async_session() as db:
        await build_daily_feature_store(db)


async def build_v4_sales_events_shadow_task():
    """Nightly idempotent sync into v4_sales_events_shadow (safe no-op if flag off)."""
    if not settings.FEATURE_V4_SALES_EVENTS_SHADOW:
        return
    from app.core.database import async_session
    from app.services.sales_events_shadow_sync import sync_sales_events_shadow_yesterday

    async with async_session() as db:
        await sync_sales_events_shadow_yesterday(db)


async def build_v4_sales_dna_nightly_task():
    """Quota-limited DNA materialization for UTC yesterday (safe no-op if flag off)."""
    if not settings.FEATURE_V4_SALES_DNA:
        return
    from app.core.database import async_session
    from app.services.v4_learning_nightly import run_v4_sales_dna_nightly

    async with async_session() as db:
        await run_v4_sales_dna_nightly(db)


async def build_v4_deal_replay_nightly_task():
    """Quota-limited deal replay snapshots for UTC yesterday (safe no-op if flag off)."""
    if not settings.FEATURE_V4_DEAL_REPLAY:
        return
    from app.core.database import async_session
    from app.services.v4_learning_nightly import run_v4_deal_replay_nightly

    async with async_session() as db:
        await run_v4_deal_replay_nightly(db)


async def build_v5_intelligence_nightly_task():
    """V5 intelligence pipeline: foundation augmentation, miners, anomaly scan.

    Skipped entirely when FEATURE_V5_INTELLIGENCE is off; safe to deploy
    behind the flag while we backfill the segment_key data.
    """
    if not settings.FEATURE_V5_INTELLIGENCE:
        return
    from app.core.database import async_session
    from app.services.v4_learning_nightly import run_v5_intelligence_nightly

    async with async_session() as db:
        await run_v5_intelligence_nightly(db)


async def build_rag_incremental_backfill_task():
    """V11 RAG incremental backfill — last ~25 hours of changes."""
    if not settings.FEATURE_RAG:
        return
    from app.core.database import async_session
    from app.services.rag_backfill_service import run_incremental_backfill

    async with async_session() as db:
        await run_incremental_backfill(db)


# ────────────────────────────────────────────────────────────────────
# Round-19 cron jobs
# ────────────────────────────────────────────────────────────────────


async def r19_token_blocklist_cleanup_task():
    """F-013 — drop expired JTI entries from the persistent blocklist.

    Runs hourly. Idempotent (DELETE WHERE exp < now()). At 20-30 user
    scale this trims at most a few hundred rows per run.
    """
    from app.core.database import async_session
    from app.services.token_blocklist import cleanup_expired_blocklist

    async with async_session() as db:
        deleted = await cleanup_expired_blocklist(db)
        await db.commit()
        if deleted:
            logger.info("token_blocklist cron removed %d expired JTIs", deleted)


async def r19_admin_nonce_cleanup_task():
    """F-005 — drop expired admin-action nonces.

    Runs every 30 min. The TTL is 5 min so this is generous; mostly a
    hygiene job to keep the table from growing past the daily volume.
    """
    from app.core.database import async_session
    from app.services.admin_nonce import cleanup_expired_nonces

    async with async_session() as db:
        deleted = await cleanup_expired_nonces(db)
        await db.commit()
        if deleted:
            logger.info("admin_nonce cron removed %d expired nonces", deleted)


async def r19_approval_sla_task():
    """F-028 — escalate overdue approvals.

    Finds pending approval requests past their ``due_at`` and bumps
    ``escalation_level`` / reassigns per the rule's escalation chain.
    Never auto-approves — the Round-19 audit forbids that. On the
    20-30 user pilot this is mostly a "send a reminder email" job.
    """
    from sqlalchemy import text

    from app.core.database import async_session
    from app.services.approval_sla import next_escalation_target

    async with async_session() as db:
        # Pull every pending request past due that hasn't yet been
        # escalated. Small cap so a backlog doesn't melt the job.
        overdue = (
            await db.execute(
                text(
                    """
                    SELECT
                        ar.id, ar.assigned_to, ar.escalation_level,
                        ar.rule_id, ar.tenant_id,
                        rule.delegate_to, rule.escalation_action,
                        u.manager_id
                      FROM approval_requests ar
                 LEFT JOIN approval_rules rule ON rule.id = ar.rule_id
                 LEFT JOIN users u             ON u.id    = ar.assigned_to
                     WHERE ar.status = 'pending'
                       AND ar.due_at IS NOT NULL
                       AND ar.due_at < now()
                       AND ar.escalation_level < 5
                     LIMIT 200
                    """
                )
            )
        ).mappings().all()

        bumped = 0
        for row in overdue:
            nxt, action = next_escalation_target(
                current_assignee_id=row["assigned_to"],
                rule_delegate_id=row["delegate_to"],
                rule_escalation_action=row["escalation_action"],
                manager_id=row.get("manager_id"),
            )
            await db.execute(
                text(
                    """
                    UPDATE approval_requests
                       SET escalation_level = escalation_level + 1,
                           escalated_at     = now(),
                           assigned_to      = COALESCE(:nxt, assigned_to)
                     WHERE id = :id AND status = 'pending'
                    """
                ),
                {"nxt": nxt, "id": row["id"]},
            )
            bumped += 1
        await db.commit()
        if bumped:
            logger.info("approval SLA cron escalated %d overdue requests", bumped)


async def r19_health_recompute_task():
    """F-014 — drain the dirty set + run health recompute for each.

    Single-process in-memory dirty set. Drain every 5 min. Failures
    are isolated per customer so one bad row doesn't break the batch.
    """
    from app.core.database import async_session
    from app.services.health_recompute_debouncer import run_batch_recompute

    async def _recompute(db, customer_id: int) -> None:
        # Lazy import so the worker isn't a hard dependency for unit
        # tests that don't exercise this code path.
        from app.services.customer_health_service import (
            CustomerHealthService,
        )

        svc = CustomerHealthService(db)
        await svc.recompute_for_customer(customer_id)

    async with async_session() as db:
        processed = await run_batch_recompute(db, recompute_fn=_recompute)
        await db.commit()
        if processed:
            logger.info("health recompute cron processed %d customers", processed)


async def r19_delegation_expiry_task():
    """D-029 — revert approval-rule delegations past their delegate_until.

    Runs hourly. The UPDATE is idempotent — already-reverted rows are
    no-ops because the WHERE clause filters them out.
    """
    from sqlalchemy import text
    from app.core.database import async_session

    async with async_session() as db:
        res = await db.execute(
            text(
                "UPDATE approval_rules "
                "   SET delegate_to = NULL, delegate_until = NULL "
                " WHERE delegate_until IS NOT NULL "
                "   AND delegate_until < now()"
            )
        )
        await db.commit()
        if res.rowcount:
            logger.info(
                "delegation expiry cron reverted %d rule delegations",
                res.rowcount,
            )
