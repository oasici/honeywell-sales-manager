"""Sprint 4 — Calendar integration adapter (stub + hook for real providers).

Real OAuth flows live under ``integrations``; this module is the execution
boundary for *creating* calendar events from product flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.activity_logger import log_activity


@runtime_checkable
class CalendarAdapter(Protocol):
    """Provider-neutral calendar write surface."""

    async def schedule_meeting(
        self,
        *,
        title: str,
        start_at: datetime,
        duration_minutes: int,
        organizer: User,
        opportunity_id: int | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]: ...


@dataclass
class StubCalendarAdapter:
    """No external API calls — returns a deterministic placeholder payload."""

    async def schedule_meeting(
        self,
        *,
        title: str,
        start_at: datetime,
        duration_minutes: int,
        organizer: User,
        opportunity_id: int | None,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "adapter": "stub",
            "status": "placeholder",
            "title": title,
            "start_at": start_at.isoformat(),
            "duration_minutes": duration_minutes,
            "organizer_id": organizer.id,
            "opportunity_id": opportunity_id,
            "external_event_id": None,
            "metadata": metadata or {},
            "message": "Calendar provider not invoked (stub adapter).",
        }


def get_calendar_adapter() -> CalendarAdapter:
    """Factory — swap for GoogleCalendarAdapter when wired end-to-end."""
    return StubCalendarAdapter()


async def schedule_meeting_placeholder(
    *,
    db: AsyncSession,
    user: User,
    title: str,
    start_at: datetime,
    duration_minutes: int,
    opportunity_id: int | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    """Run the active calendar adapter (stub by default) and log intent."""
    adapter = get_calendar_adapter()
    payload = await adapter.schedule_meeting(
        title=title,
        start_at=start_at,
        duration_minutes=duration_minutes,
        organizer=user,
        opportunity_id=opportunity_id,
        metadata=metadata,
    )
    await log_activity(
        db,
        activity_type="calendar_stub",
        entity_type="user",
        entity_id=user.id,
        opportunity_id=opportunity_id,
        user_id=user.id,
        summary=f"Calendar placeholder: {title[:200]}",
        metadata=payload,
    )
    await db.flush()
    return payload
