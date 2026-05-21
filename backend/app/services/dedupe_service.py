from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import OpportunitySignal, Task


async def upsert_opportunity_signal(
    db: AsyncSession,
    *,
    opportunity_id: int,
    signal_type: str,
    severity: str = "med",
    evidence: str | None = None,
    source_type: str | None = None,
    source_id: int | None = None,
    dedupe_window_days: int = 14,
) -> OpportunitySignal:
    """Create an opportunity signal but dedupe repeated writes.

    Dedupe rules (pragmatic, backward-compatible):
    - If (source_type, source_id) exist: unique by (opportunity_id, signal_type, source_type, source_id)
    - Else: unique by (opportunity_id, signal_type, source_type, evidence) within time window
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=dedupe_window_days)

    conditions = [
        OpportunitySignal.opportunity_id == opportunity_id,
        OpportunitySignal.signal_type == signal_type,
        OpportunitySignal.created_at >= cutoff,
    ]

    if source_type is not None:
        conditions.append(OpportunitySignal.source_type == source_type)

    if source_type and source_id is not None:
        conditions.append(OpportunitySignal.source_id == source_id)
    else:
        if evidence:
            conditions.append(OpportunitySignal.evidence == evidence)

    existing = (
        await db.execute(
            select(OpportunitySignal)
            .where(and_(*conditions))
            .order_by(OpportunitySignal.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    # Round-15 Sprint 15m cohort 3 — OpportunitySignal.tenant_id NOT
    # NULL. Inherit from the parent opportunity.
    from app.models.opportunity import Opportunity

    opp_row = await db.execute(
        select(Opportunity.tenant_id).where(Opportunity.id == opportunity_id)
    )
    derived_tenant_id = opp_row.scalar_one_or_none()

    signal = OpportunitySignal(
        tenant_id=derived_tenant_id,
        opportunity_id=opportunity_id,
        signal_type=signal_type,
        severity=severity,
        evidence=evidence,
        source_type=source_type,
        source_id=source_id,
    )
    db.add(signal)
    await db.flush()
    await db.refresh(signal)
    return signal


async def upsert_task(
    db: AsyncSession,
    *,
    owner_id: int,
    title: str,
    opportunity_id: int | None = None,
    description: str | None = None,
    due_at=None,
    source: str = "rule",
    priority: str = "normal",
    status: str = "open",
    dedupe_window_days: int = 14,
) -> Task:
    """Create a task but dedupe repeated writes for open tasks."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=dedupe_window_days)

    existing = (
        await db.execute(
            select(Task)
            .where(
                and_(
                    Task.owner_id == owner_id,
                    Task.opportunity_id == opportunity_id,
                    Task.source == source,
                    Task.status == status,
                    Task.title == title,
                    Task.created_at >= cutoff,
                )
            )
            .order_by(Task.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing:
        return existing

    # Round-16 N15-DB-3 cohort-9 — Task.tenant_id is now NOT NULL.
    # Derive from the parent opportunity first (preferred — keeps the
    # task in the same tenant as the deal it tracks), falling back to
    # the owner's tenant when there is no opportunity link (rare:
    # standalone tasks created from rep dashboards). Matches the
    # pattern in ``upsert_opportunity_signal`` above.
    derived_tenant_id: int | None = None
    if opportunity_id is not None:
        from app.models.opportunity import Opportunity

        opp_row = await db.execute(
            select(Opportunity.tenant_id).where(Opportunity.id == opportunity_id)
        )
        derived_tenant_id = opp_row.scalar_one_or_none()
    if derived_tenant_id is None:
        from app.models.user import User

        owner_row = await db.execute(
            select(User.tenant_id).where(User.id == owner_id)
        )
        derived_tenant_id = owner_row.scalar_one_or_none()

    task = Task(
        tenant_id=derived_tenant_id,
        owner_id=owner_id,
        opportunity_id=opportunity_id,
        title=title,
        description=description,
        due_at=due_at,
        status=status,
        source=source,
        priority=priority,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return task

