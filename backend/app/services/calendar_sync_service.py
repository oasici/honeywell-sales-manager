"""Calendar sync service (V9) — OAuth bookkeeping + meeting auto-log.

The actual OAuth dance with Google/Microsoft lives in
``calendar_adapter`` (already shipped); this module owns the bridge
between an external event and an internal Opportunity / OpportunityEvent.

Public surface:
- ``link_meeting_to_opportunity(...)`` — explicit manual link
- ``auto_log_meeting(...)`` — match by attendee email + create
  OpportunityEvent + log_activity
- ``ensure_token_fresh(...)`` — placeholder for OAuth refresh, plugs
  into the existing ``app.core.crypto`` if configured
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.meeting_booking import MeetingBooking
from app.models.opportunity import Opportunity, OpportunityEvent
from app.models.v9_calendar import CalendarConnection, MeetingAutoLink

logger = logging.getLogger(__name__)


# ─────────────────────── auto-link by attendee email ─────────────────


async def auto_log_meeting(
    db: AsyncSession,
    *,
    meeting_booking_id: int,
    external_event_id: str | None = None,
) -> MeetingAutoLink | None:
    """Resolve an opportunity for the booking and persist the link.

    Resolution order:
      1. Booking already references an opportunity_id → use it.
      2. Booker email matches a customer.email → use that customer's
         most-recent active opportunity.
      3. No match → return None (caller decides to alert / skip).
    """
    booking = await db.get(MeetingBooking, meeting_booking_id)
    if booking is None:
        return None

    matched_opp_id: int | None = getattr(booking, "opportunity_id", None)
    matched_cust_id: int | None = getattr(booking, "customer_id", None)
    matched_by = "explicit"
    confidence = 1.0 if matched_opp_id else 0.0

    if matched_opp_id is None:
        cust = (
            await db.execute(
                select(Customer).where(Customer.email == booking.booker_email)
            )
        ).scalar_one_or_none()
        if cust is not None:
            matched_cust_id = cust.id
            matched_by = "attendee_email"
            opp = (
                await db.execute(
                    select(Opportunity)
                    .where(Opportunity.customer_id == cust.id)
                    .where(Opportunity.status == "active")
                    .order_by(Opportunity.updated_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if opp is not None:
                matched_opp_id = opp.id
                confidence = 0.7

    # Persist link (idempotent on (booking, external_event_id))
    existing = (
        await db.execute(
            select(MeetingAutoLink)
            .where(MeetingAutoLink.meeting_booking_id == meeting_booking_id)
            .where(MeetingAutoLink.external_event_id == external_event_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    link = MeetingAutoLink(
        meeting_booking_id=meeting_booking_id,
        external_event_id=external_event_id,
        opportunity_id=matched_opp_id,
        customer_id=matched_cust_id,
        matched_by=matched_by,
        confidence=confidence,
    )
    db.add(link)
    await db.flush()

    # Mirror to OpportunityEvent so V4/V5 timeline picks it up.
    if matched_opp_id is not None:
        db.add(
            OpportunityEvent(
                opportunity_id=matched_opp_id,
                event_type="meeting_logged",
                entity_type="meeting_booking",
                entity_id=meeting_booking_id,
                description=f"Auto-logged meeting with {booking.booker_email}",
                occurred_at=booking.scheduled_at or datetime.now(timezone.utc),
            )
        )
        await db.flush()

    return link


# ─────────────────────── explicit manual link ────────────────────────


async def link_meeting_to_opportunity(
    db: AsyncSession,
    *,
    meeting_booking_id: int,
    opportunity_id: int,
) -> MeetingAutoLink:
    """Manager/rep-driven link override."""
    existing = (
        await db.execute(
            select(MeetingAutoLink)
            .where(MeetingAutoLink.meeting_booking_id == meeting_booking_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.opportunity_id = opportunity_id
        existing.matched_by = "manual"
        existing.confidence = 1.0
        await db.flush()
        return existing

    link = MeetingAutoLink(
        meeting_booking_id=meeting_booking_id,
        opportunity_id=opportunity_id,
        matched_by="manual",
        confidence=1.0,
    )
    db.add(link)
    await db.flush()
    return link


# ─────────────────────── connection helpers ──────────────────────────


async def list_calendar_connections(
    db: AsyncSession, *, user_id: int
) -> list[CalendarConnection]:
    rows = (
        await db.execute(
            select(CalendarConnection).where(CalendarConnection.user_id == user_id)
        )
    ).scalars().all()
    return list(rows)


async def upsert_calendar_connection(
    db: AsyncSession,
    *,
    user_id: int,
    provider: str,
    calendar_id: str | None = None,
    access_token: str | None = None,
    refresh_token: str | None = None,
    expires_at: datetime | None = None,
) -> CalendarConnection:
    """Idempotent upsert per (user_id, provider).

    Tokens are written **as-is** here; production deployments should
    pre-encrypt via ``app.core.crypto.encrypt`` before calling. The
    column type is ``Text`` so it accepts both raw and encrypted blobs
    while the encryption migration matures.
    """
    existing = (
        await db.execute(
            select(CalendarConnection)
            .where(CalendarConnection.user_id == user_id)
            .where(CalendarConnection.provider == provider)
        )
    ).scalar_one_or_none()

    if existing is None:
        conn = CalendarConnection(
            user_id=user_id,
            provider=provider,
            calendar_id=calendar_id,
            oauth_token_encrypted=access_token,
            refresh_token_encrypted=refresh_token,
            expires_at=expires_at,
            is_active=bool(access_token),
        )
        db.add(conn)
        await db.flush()
        return conn

    if calendar_id is not None:
        existing.calendar_id = calendar_id
    if access_token is not None:
        existing.oauth_token_encrypted = access_token
        existing.is_active = True
    if refresh_token is not None:
        existing.refresh_token_encrypted = refresh_token
    if expires_at is not None:
        existing.expires_at = expires_at
    await db.flush()
    return existing


async def ensure_token_fresh(
    db: AsyncSession, *, connection_id: int
) -> CalendarConnection | None:
    """Stub for OAuth refresh — V9 returns the row as-is.

    Production replaces this with a provider-specific refresh call
    (Google: POST /token with grant_type=refresh_token; Microsoft:
    POST oauth2/v2.0/token). Token is then re-encrypted + persisted.
    """
    conn = await db.get(CalendarConnection, connection_id)
    if conn is None:
        return None
    if conn.expires_at and conn.expires_at < datetime.now(timezone.utc):
        logger.info("Calendar token expired for conn=%s — refresh stub", conn.id)
    return conn
