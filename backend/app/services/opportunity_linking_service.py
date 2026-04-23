from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.enums import OpportunityStage, UserRole
from app.models.opportunity import Opportunity, OpportunityEvent
from app.models.user import User


async def ensure_opportunity_for_email(
    db: AsyncSession,
    *,
    email: EmailRequest,
    owner_hint: int | None,
) -> int:
    """Ensure an opportunity exists for this email's customer/thread.

    Contract:
    - Returns an opportunity_id (existing or newly created).
    - Does NOT mutate `email` or commit; caller should persist changes.
    """
    if email.opportunity_id:
        return int(email.opportunity_id)

    # Reuse: if another email in same thread already linked to an opportunity, reuse that.
    if email.thread_id and email.customer_id:
        existing = await db.execute(
            select(EmailRequest.opportunity_id)
            .where(
                EmailRequest.customer_id == email.customer_id,
                EmailRequest.thread_id == email.thread_id,
                EmailRequest.opportunity_id.isnot(None),
            )
            .order_by(EmailRequest.created_at.desc())
            .limit(1)
        )
        opp_id = existing.scalar_one_or_none()
        if opp_id:
            return int(opp_id)

    owner_id = owner_hint
    if owner_id is None and email.customer_id:
        cust = (await db.execute(select(Customer).where(Customer.id == email.customer_id))).scalar_one_or_none()
        owner_id = cust.created_by if cust else None

    if owner_id is None:
        manager = (
            await db.execute(
                select(User)
                .where(User.role == UserRole.SALES_MANAGER.value, User.is_active.is_(True))
                .order_by(User.id.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        owner_id = manager.id if manager else None

    if owner_id is None:
        any_user = (
            await db.execute(
                select(User).where(User.is_active.is_(True)).order_by(User.id.asc()).limit(1)
            )
        ).scalar_one_or_none()
        owner_id = any_user.id if any_user else None

    if owner_id is None:
        raise BadRequestException("Opportunity olusturmak icin owner bulunamadi")

    subject = (email.subject or "").strip()
    title = subject[:120] if subject else f"E-posta #{email.id} - Yeni Firsat"

    opp = Opportunity(
        title=title,
        stage=OpportunityStage.PROSPECTING.value,
        customer_id=email.customer_id,
        owner_id=int(owner_id),
        status="active",
        probability=0.10,
    )
    db.add(opp)
    await db.flush()

    db.add(
        OpportunityEvent(
            opportunity_id=opp.id,
            event_type="email",
            entity_type="email",
            entity_id=email.id,
            description=f"E-posta ile baslatildi: {title}",
        )
    )
    await db.flush()

    return int(opp.id)

