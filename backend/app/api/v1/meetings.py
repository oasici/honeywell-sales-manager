from __future__ import annotations

import random
import string
import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.models.meeting_link import MeetingLink
from app.models.meeting_booking import MeetingBooking
from app.models.user import User
from app.services.activity_logger import log_activity
from app.services.notification_service import create_notification
from app.schemas.meeting import (
    MeetingBookingCreateResponse,
    MeetingBookingListResponse,
    MeetingBookingPagePublicResponse,
    MeetingLinkEnvelope,
    MeetingLinkListResponse,
    MeetingMessageResponse,
    MeetingPlaceholderResponse,
)

router = APIRouter(prefix="/meetings", tags=["Meetings"])

RANDOM_SUFFIX_LENGTH = 4


def _generate_slug(full_name: str) -> str:
    """Generate a URL-friendly slug from a user's full name + random chars."""
    base = re.sub(r"[^a-z0-9]+", "-", full_name.lower()).strip("-")
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=RANDOM_SUFFIX_LENGTH))
    return f"{base}-{suffix}"


class CreateLinkRequest(BaseModel):
    title: str
    duration_minutes: int = 30


class BookingRequest(BaseModel):
    booker_name: str
    booker_email: str
    scheduled_at: datetime
    notes: str | None = None


class SchedulePlaceholderBody(BaseModel):
    """Sprint 4 — calendar adapter stub: records intent without external calendar write."""

    title: str
    start_at: datetime
    duration_minutes: int = 30
    opportunity_id: int | None = None


@router.post("/schedule-placeholder", response_model=MeetingPlaceholderResponse)
async def schedule_meeting_placeholder(
    body: SchedulePlaceholderBody,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.calendar_adapter import schedule_meeting_placeholder as run_stub

    payload = await run_stub(
        db=db,
        user=current_user,
        title=body.title,
        start_at=body.start_at,
        duration_minutes=body.duration_minutes,
        opportunity_id=body.opportunity_id,
        metadata=None,
    )
    await db.commit()
    return {"data": payload}


@router.get("/links", response_model=MeetingLinkListResponse)
async def list_links(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the current user's meeting links."""
    result = await db.execute(
        select(MeetingLink)
        .where(MeetingLink.user_id == current_user.id)
        .order_by(MeetingLink.created_at.desc())
    )
    links = result.scalars().all()
    return {
        "data": [
            {
                "id": lnk.id,
                "slug": lnk.slug,
                "title": lnk.title,
                "duration_minutes": lnk.duration_minutes,
                "is_active": lnk.is_active,
                "created_at": lnk.created_at.isoformat() if lnk.created_at else None,
            }
            for lnk in links
        ]
    }


@router.post("/links", response_model=MeetingLinkEnvelope)
async def create_link(
    body: CreateLinkRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new meeting link with an auto-generated slug."""
    slug = _generate_slug(current_user.full_name)
    link = MeetingLink(
        user_id=current_user.id,
        # Round-15 Sprint 15n cohort 4 — meeting_links.tenant_id NOT NULL.
        tenant_id=current_user.tenant_id,
        slug=slug,
        title=body.title,
        duration_minutes=body.duration_minutes,
    )
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return {
        "data": {
            "id": link.id,
            "slug": link.slug,
            "title": link.title,
            "duration_minutes": link.duration_minutes,
            "is_active": link.is_active,
            "booking_url": f"/api/v1/meetings/book/{link.slug}",
            "created_at": link.created_at.isoformat() if link.created_at else None,
        }
    }


@router.delete("/links/{link_id}", response_model=MeetingMessageResponse)
async def deactivate_link(
    link_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a meeting link."""
    result = await db.execute(
        select(MeetingLink).where(
            MeetingLink.id == link_id,
            MeetingLink.user_id == current_user.id,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise NotFoundException("Toplanti linki bulunamadi")

    link.is_active = False
    await db.commit()
    return {"data": {"message": "Toplanti linki devre disi birakildi"}}


@router.get("/book/{slug}", response_model=MeetingBookingPagePublicResponse)
async def get_booking_page(
    slug: str,
    db: AsyncSession = Depends(get_db),
):
    """PUBLIC. Return meeting link info and availability."""
    result = await db.execute(
        select(MeetingLink).where(
            MeetingLink.slug == slug,
            MeetingLink.is_active.is_(True),
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise NotFoundException("Toplanti linki bulunamadi")

    return {
        "data": {
            "title": link.title,
            "duration_minutes": link.duration_minutes,
            "availability_json": link.availability_json,
        }
    }


@router.post("/book/{slug}", response_model=MeetingBookingCreateResponse)
async def create_booking(
    slug: str,
    body: BookingRequest,
    db: AsyncSession = Depends(get_db),
):
    """PUBLIC. Book a meeting slot."""
    result = await db.execute(
        select(MeetingLink).where(
            MeetingLink.slug == slug,
            MeetingLink.is_active.is_(True),
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise NotFoundException("Toplanti linki bulunamadi")

    booking = MeetingBooking(
        meeting_link_id=link.id,
        booker_name=body.booker_name,
        booker_email=body.booker_email,
        scheduled_at=body.scheduled_at,
        notes=body.notes,
    )
    db.add(booking)
    await db.flush()

    await log_activity(
        db,
        activity_type="meeting_booked",
        entity_type="meeting_booking",
        entity_id=booking.id,
        user_id=link.user_id,
        summary=f"{body.booker_name} ({body.booker_email}) toplanti rezervasyonu yapti",
    )

    await create_notification(
        db,
        user_id=link.user_id,
        type="meeting_booked",
        title="Yeni Toplanti Rezervasyonu",
        message=f"{body.booker_name} ({body.booker_email}) - {link.title}",
        entity_type="meeting_booking",
        entity_id=booking.id,
    )

    await db.commit()

    return {
        "data": {
            "id": booking.id,
            "scheduled_at": booking.scheduled_at.isoformat(),
            "status": booking.status,
        }
    }


@router.get("/bookings")
async def list_bookings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List bookings for the current user's meeting links."""
    link_ids_query = select(MeetingLink.id).where(
        MeetingLink.user_id == current_user.id
    )
    result = await db.execute(
        select(MeetingBooking)
        .where(MeetingBooking.meeting_link_id.in_(link_ids_query))
        .order_by(MeetingBooking.scheduled_at.desc())
    )
    bookings = result.scalars().all()
    return {
        "data": [
            {
                "id": b.id,
                "meeting_link_id": b.meeting_link_id,
                "booker_name": b.booker_name,
                "booker_email": b.booker_email,
                "scheduled_at": b.scheduled_at.isoformat(),
                "notes": b.notes,
                "status": b.status,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in bookings
        ]
    }
