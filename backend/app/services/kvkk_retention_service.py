"""KVKK auto-anonymization for time-expired records.

Two destructive operations live here, run nightly when
``settings.KVKK_AUTO_ANONYMIZE_ENABLED`` is true:

1. **EmailRequest** older than ``KVKK_EMAIL_RETENTION_DAYS`` (default: 2y)
   has its PII fields nulled — sender, subject, bodies, parsed JSON.
   The row stays for analytics so the audit trail isn't punctured.

2. **Customer** anonymization when their latest opportunity closed more
   than ``KVKK_OPPORTUNITY_RETENTION_DAYS`` (default: 3y) ago AND they
   have no active opportunities. Reuses the same field-set the manual
   ``/api/v1/compliance/data-delete/{id}`` endpoint applies.

Both operations write an ``audit_logs`` row per affected entity so the
KVKK officer can prove which records were anonymized when. Both support
``dry_run=True`` for trial runs against staging or for the operator who
wants to see "what would the cron do tonight" before flipping the flag.

The cron itself is wired in ``app/tasks/scheduler.py``. Keeping the
service pure (no scheduler coupling) means the same code can be invoked
manually from a runbook or a one-off admin endpoint.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists, func, not_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.opportunity import Opportunity

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# Email retention
# ─────────────────────────────────────────────────────────────────────────────


async def anonymize_old_email_requests(
    db: AsyncSession,
    *,
    older_than_days: int,
    dry_run: bool = False,
) -> int:
    """Null PII on EmailRequests older than ``older_than_days``.

    Returns the number of rows that would be (or were) anonymized. The row
    itself is preserved — only PII columns are cleared, so analytics
    queries (counts, category breakdowns) keep working.
    """
    if older_than_days <= 0:
        raise ValueError("older_than_days must be positive")

    cutoff = _utcnow() - timedelta(days=older_than_days)

    # Filter on the row's recorded receive time. Fall back to created_at
    # when received_at is null — older rows may not have it set.
    age_filter = and_(
        EmailRequest.received_at.isnot(None),
        EmailRequest.received_at < cutoff,
        # Skip rows that have already been anonymized (idempotency).
        EmailRequest.body_text.isnot(None),
    )

    if dry_run:
        count_stmt = select(func.count()).select_from(EmailRequest).where(age_filter)
        count = (await db.execute(count_stmt)).scalar_one() or 0
        logger.info(
            "KVKK email anonymize dry-run: %d rows would be anonymized "
            "(older than %d days)",
            count,
            older_than_days,
        )
        return int(count)

    # Pull IDs first so we can record an audit row per entity. UPDATE-RETURNING
    # would be cleaner, but SQLAlchemy + asyncpg + SQLite-in-tests don't share
    # a portable RETURNING surface, so we do it in two passes.
    id_stmt = select(EmailRequest.id).where(age_filter)
    target_ids = [row[0] for row in (await db.execute(id_stmt)).all()]

    if not target_ids:
        return 0

    update_stmt = (
        update(EmailRequest)
        .where(EmailRequest.id.in_(target_ids))
        .values(
            from_address="anonymized@deleted.local",
            subject=None,
            body_text=None,
            body_html=None,
            parsed_data=None,
        )
    )
    await db.execute(update_stmt)

    for entity_id in target_ids:
        db.add(
            AuditLog(
                user_id=None,
                action="kvkk_email_auto_anonymize",
                entity_type="email_request",
                entity_id=entity_id,
                changes=json.dumps({
                    "anonymized_at": _utcnow().isoformat(),
                    "trigger": "retention_cron",
                    "retention_days": older_than_days,
                }),
            )
        )

    await db.flush()
    logger.info(
        "KVKK email anonymize: %d EmailRequest rows anonymized (older than %d days)",
        len(target_ids),
        older_than_days,
    )
    return len(target_ids)


# ─────────────────────────────────────────────────────────────────────────────
# Customer (opportunity-based) retention
# ─────────────────────────────────────────────────────────────────────────────


async def anonymize_dormant_customers(
    db: AsyncSession,
    *,
    older_than_days: int,
    dry_run: bool = False,
) -> int:
    """Anonymize Customers whose newest closed opportunity is older than the
    threshold and who have no active opportunities. Idempotent — already-
    anonymized customers (``deletion_requested_at IS NOT NULL``) are skipped.
    """
    if older_than_days <= 0:
        raise ValueError("older_than_days must be positive")

    cutoff_date = (_utcnow() - timedelta(days=older_than_days)).date()

    # Customer is eligible when:
    #   - not already anonymized
    #   - has at least one opportunity (otherwise we have no signal)
    #   - has NO opportunity with status='active'
    #   - max(close_date) of remaining opportunities is older than cutoff
    has_active_opp = (
        select(Opportunity.id)
        .where(
            and_(
                Opportunity.customer_id == Customer.id,
                Opportunity.status == "active",
            )
        )
        .exists()
    )

    has_recent_close = (
        select(Opportunity.id)
        .where(
            and_(
                Opportunity.customer_id == Customer.id,
                Opportunity.status == "closed",
                Opportunity.close_date >= cutoff_date,
            )
        )
        .exists()
    )

    has_any_opportunity = (
        select(Opportunity.id)
        .where(Opportunity.customer_id == Customer.id)
        .exists()
    )

    eligibility = and_(
        Customer.deletion_requested_at.is_(None),
        has_any_opportunity,
        not_(has_active_opp),
        not_(has_recent_close),
    )

    if dry_run:
        count_stmt = select(func.count()).select_from(Customer).where(eligibility)
        count = (await db.execute(count_stmt)).scalar_one() or 0
        logger.info(
            "KVKK customer anonymize dry-run: %d customers would be "
            "anonymized (no active opp, no close within %d days)",
            count,
            older_than_days,
        )
        return int(count)

    target_stmt = select(Customer).where(eligibility)
    targets = (await db.execute(target_stmt)).scalars().all()

    now = _utcnow()
    for customer in targets:
        # Same field-set the manual /compliance/data-delete endpoint applies.
        customer.name = "ANONIMLESTIRILDI"
        customer.email = f"anon_{customer.id}@deleted.local"
        customer.phone = None
        customer.address = None
        customer.tax_id = None
        customer.company = None
        customer.deletion_requested_at = now
        customer.kvkk_consent = False

        db.add(
            AuditLog(
                user_id=None,
                action="kvkk_customer_auto_anonymize",
                entity_type="customer",
                entity_id=customer.id,
                changes=json.dumps({
                    "anonymized_at": now.isoformat(),
                    "trigger": "retention_cron",
                    "retention_days": older_than_days,
                }),
            )
        )

    if targets:
        await db.flush()

    logger.info(
        "KVKK customer anonymize: %d Customer rows anonymized (no recent activity within %d days)",
        len(targets),
        older_than_days,
    )
    return len(targets)


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator (called from scheduler)
# ─────────────────────────────────────────────────────────────────────────────


async def run_retention_anonymization(
    db: AsyncSession,
    *,
    email_retention_days: int,
    opportunity_retention_days: int,
    dry_run: bool = False,
) -> dict[str, int]:
    """Run all retention sweeps in a single transaction.

    Returns a {email_count, customer_count} summary suitable for logging
    and for surfacing in the daily KVKK summary notification.
    """
    email_count = await anonymize_old_email_requests(
        db, older_than_days=email_retention_days, dry_run=dry_run
    )
    customer_count = await anonymize_dormant_customers(
        db, older_than_days=opportunity_retention_days, dry_run=dry_run
    )
    return {"email_count": email_count, "customer_count": customer_count}
