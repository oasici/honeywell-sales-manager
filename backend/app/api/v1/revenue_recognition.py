"""Revenue Recognition API — schedule-based revenue tracking and recognition."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.contract import Contract
from app.models.revenue_recognition import RevenueSchedule, RevenueScheduleEntry
from app.models.user import User
from app.services.tenant_context import assert_same_tenant, scoped_for_user
from app.schemas.common import PaginatedResponse
from app.schemas.round15_pagination import RevenueScheduleRow

# Routes use mixed-path convention (/revenue-schedules/ and /revenue-recognition/dashboard)
# rather than a shared router prefix, which is intentional for semantic clarity.
router = APIRouter(tags=["Revenue Recognition"])

RECOGNITION_TYPES = {"immediate", "straight_line", "milestone", "usage"}


def _require_rev_rec() -> None:
    """Dependency: reject if FEATURE_REV_REC is off."""
    if not settings.FEATURE_REV_REC:
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic Schemas ──


class ScheduleCreate(BaseModel):
    contract_id: int
    recognition_type: str = Field(default="straight_line", max_length=20)
    start_date: datetime
    end_date: datetime
    total_amount: float = Field(gt=0)
    currency: str = Field(default="TRY", max_length=10)


# ── Serializers ──


def _serialize_schedule(s: RevenueSchedule) -> dict:
    return {
        "id": s.id,
        # Round-4 R4-DTO-6 — round-trip tenant_id (R4-TEN-8).
        "tenant_id": getattr(s, "tenant_id", None),
        "contract_id": s.contract_id,
        "recognition_type": s.recognition_type,
        "start_date": s.start_date.isoformat() if s.start_date else None,
        "end_date": s.end_date.isoformat() if s.end_date else None,
        "total_amount": s.total_amount,
        "recognized_amount": s.recognized_amount,
        "currency": s.currency,
        "created_by": s.created_by,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _serialize_entry(e: RevenueScheduleEntry) -> dict:
    return {
        "id": e.id,
        "tenant_id": getattr(e, "tenant_id", None),
        "schedule_id": e.schedule_id,
        "period": e.period,
        "amount": e.amount,
        "recognized_amount": e.recognized_amount,
        "status": e.status,
        "recognized_at": e.recognized_at.isoformat() if e.recognized_at else None,
        "notes": e.notes,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def _months_between(start: datetime, end: datetime) -> list[str]:
    """Return list of YYYY-MM strings from start month to end month inclusive."""
    periods: list[str] = []
    year, month = start.year, start.month
    end_year, end_month = end.year, end.month
    while (year, month) <= (end_year, end_month):
        periods.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            month = 1
            year += 1
    return periods


# ── Endpoints ──


@router.get("/revenue-schedules/", response_model=PaginatedResponse[RevenueScheduleRow])
async def list_schedules(
    contract_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    _: None = Depends(_require_rev_rec),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List revenue schedules, optionally filtered by contract.

    Round-5 Phase 7 — canonical pagination envelope. Bounded at
    ``page_size <= 100`` to keep the per-row entries-fan-out under
    control (each schedule does an additional entries query).
    """
    import math as _math

    query = scoped_for_user(
        select(RevenueSchedule).order_by(RevenueSchedule.id.desc()),
        current_user,
        column=RevenueSchedule.tenant_id,
    )
    if contract_id is not None:
        query = query.where(RevenueSchedule.contract_id == contract_id)

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    schedules = result.scalars().all()

    # Include entries for each schedule
    serialized = []
    for s in schedules:
        data = _serialize_schedule(s)
        entries_result = await db.execute(
            select(RevenueScheduleEntry)
            .where(RevenueScheduleEntry.schedule_id == s.id)
            .order_by(RevenueScheduleEntry.period)
        )
        data["entries"] = [_serialize_entry(e) for e in entries_result.scalars().all()]
        # Include contract title
        contract_result = await db.execute(
            select(Contract).where(Contract.id == s.contract_id)
        )
        contract = contract_result.scalar_one_or_none()
        data["contract"] = {"title": contract.title} if contract and hasattr(contract, "title") else None
        serialized.append(data)

    return {
        "items": serialized,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": _math.ceil(total / page_size) if total > 0 else 0,
    }


@router.post("/revenue-schedules/", status_code=201)
async def create_schedule(
    body: ScheduleCreate,
    _: None = Depends(_require_rev_rec),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new revenue schedule."""
    if body.recognition_type not in RECOGNITION_TYPES:
        raise BadRequestException(
            f"Invalid recognition_type. Must be one of: {', '.join(sorted(RECOGNITION_TYPES))}"
        )
    if body.end_date <= body.start_date:
        raise BadRequestException("end_date must be after start_date")

    contract_result = await db.execute(
        select(Contract).where(Contract.id == body.contract_id)
    )
    contract = contract_result.scalar_one_or_none()
    if contract is None:
        raise NotFoundException("Contract not found")
    # Round-4 R4-TEN-8 — block creating a schedule attached to a
    # foreign tenant's contract.
    assert_same_tenant(contract, current_user, exception_cls=NotFoundException)

    schedule = RevenueSchedule(
        tenant_id=getattr(current_user, "tenant_id", None),
        contract_id=body.contract_id,
        recognition_type=body.recognition_type,
        start_date=body.start_date,
        end_date=body.end_date,
        total_amount=body.total_amount,
        currency=body.currency,
        created_by=current_user.id,
    )
    db.add(schedule)
    await db.commit()
    await db.refresh(schedule)
    return _serialize_schedule(schedule)


@router.get("/revenue-schedules/{schedule_id}")
async def get_schedule(
    schedule_id: int,
    _: None = Depends(_require_rev_rec),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get schedule detail including all entries."""
    result = await db.execute(
        select(RevenueSchedule).where(RevenueSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise NotFoundException("Revenue schedule not found")
    assert_same_tenant(schedule, current_user, exception_cls=NotFoundException)

    entries_result = await db.execute(
        select(RevenueScheduleEntry)
        .where(RevenueScheduleEntry.schedule_id == schedule_id)
        .order_by(RevenueScheduleEntry.period)
    )
    entries = entries_result.scalars().all()

    data = _serialize_schedule(schedule)
    data["entries"] = [_serialize_entry(e) for e in entries]
    return data


@router.post("/revenue-schedules/{schedule_id}/generate-entries", status_code=201)
async def generate_entries(
    schedule_id: int,
    _: None = Depends(_require_rev_rec),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate monthly entries by splitting total_amount evenly across months."""
    result = await db.execute(
        select(RevenueSchedule).where(RevenueSchedule.id == schedule_id)
    )
    schedule = result.scalar_one_or_none()
    if schedule is None:
        raise NotFoundException("Revenue schedule not found")
    assert_same_tenant(schedule, current_user, exception_cls=NotFoundException)

    existing_result = await db.execute(
        select(RevenueScheduleEntry)
        .where(RevenueScheduleEntry.schedule_id == schedule_id)
        .order_by(RevenueScheduleEntry.period)
    )
    existing_entries = existing_result.scalars().all()
    if existing_entries:
        return {"generated": 0, "entries": [_serialize_entry(e) for e in existing_entries], "message": "Kayitlar zaten mevcut"}

    periods = _months_between(schedule.start_date, schedule.end_date)
    if not periods:
        raise BadRequestException("No periods found between start_date and end_date")

    per_month = round(schedule.total_amount / len(periods), 2)
    # Assign any rounding remainder to the last period
    remainder = round(schedule.total_amount - per_month * len(periods), 2)

    entries: list[RevenueScheduleEntry] = []
    for idx, period in enumerate(periods):
        amount = per_month + (remainder if idx == len(periods) - 1 else 0.0)
        entry = RevenueScheduleEntry(
            tenant_id=schedule.tenant_id,
            schedule_id=schedule_id,
            period=period,
            amount=amount,
        )
        db.add(entry)
        entries.append(entry)

    await db.commit()
    for entry in entries:
        await db.refresh(entry)

    return {"generated": len(entries), "entries": [_serialize_entry(e) for e in entries]}


@router.patch("/revenue-schedules/{schedule_id}/entries/{entry_id}/recognize")
async def recognize_entry(
    schedule_id: int,
    entry_id: int,
    _: None = Depends(_require_rev_rec),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a schedule entry as recognized and update schedule totals."""
    entry_result = await db.execute(
        select(RevenueScheduleEntry).where(
            RevenueScheduleEntry.id == entry_id,
            RevenueScheduleEntry.schedule_id == schedule_id,
        )
    )
    entry = entry_result.scalar_one_or_none()
    if entry is None:
        raise NotFoundException("Entry not found")
    # Round-4 R4-TEN-8 — recognizing a foreign tenant's entry would
    # corrupt their books (irreversible).
    assert_same_tenant(entry, current_user, exception_cls=NotFoundException)

    if entry.status == "recognized":
        raise BadRequestException("Entry is already recognized")

    schedule_result = await db.execute(
        select(RevenueSchedule).where(RevenueSchedule.id == schedule_id)
    )
    schedule = schedule_result.scalar_one_or_none()
    if schedule is None:
        raise NotFoundException("Revenue schedule not found")
    assert_same_tenant(schedule, current_user, exception_cls=NotFoundException)

    entry.status = "recognized"
    entry.recognized_amount = entry.amount
    entry.recognized_at = datetime.now(timezone.utc)
    schedule.recognized_amount = round(schedule.recognized_amount + entry.amount, 2)

    await db.commit()
    await db.refresh(entry)
    await db.refresh(schedule)

    return {
        "entry": _serialize_entry(entry),
        "schedule_recognized_amount": schedule.recognized_amount,
    }


@router.get("/revenue-recognition/dashboard")
async def recognition_dashboard(
    _: None = Depends(_require_rev_rec),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Summary dashboard — tenant-scoped (R4-TEN-8)."""
    total_scheduled_result = await db.execute(
        scoped_for_user(
            select(func.coalesce(func.sum(RevenueSchedule.total_amount), 0.0)),
            current_user,
            column=RevenueSchedule.tenant_id,
        )
    )
    total_scheduled: float = total_scheduled_result.scalar_one()

    total_recognized_result = await db.execute(
        scoped_for_user(
            select(func.coalesce(func.sum(RevenueSchedule.recognized_amount), 0.0)),
            current_user,
            column=RevenueSchedule.tenant_id,
        )
    )
    total_recognized: float = total_recognized_result.scalar_one()

    current_period = datetime.now(timezone.utc).strftime("%Y-%m")
    this_month_result = await db.execute(
        scoped_for_user(
            select(func.coalesce(func.sum(RevenueScheduleEntry.amount), 0.0)),
            current_user,
            column=RevenueScheduleEntry.tenant_id,
        ).where(
            RevenueScheduleEntry.period == current_period,
            RevenueScheduleEntry.status == "pending",
        )
    )
    this_month_pending: float = this_month_result.scalar_one()

    recognition_rate_pct = (
        round(total_recognized / total_scheduled * 100, 2)
        if total_scheduled > 0
        else 0.0
    )

    return {
        "total_scheduled": total_scheduled,
        "total_recognized": total_recognized,
        "this_month_pending": this_month_pending,
        "recognition_rate_pct": recognition_rate_pct,
    }
