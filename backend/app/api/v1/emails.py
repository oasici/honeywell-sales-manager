import json
import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import Role, get_current_user, require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.email_request import EmailRequest
from app.models.quote_item import QuoteItem
from app.models.user import User

router = APIRouter(prefix="/emails", tags=["Emails"])


@router.get("/")
async def list_emails(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filter by processing status"),
    review_status: str | None = Query(None, description="Filter by review status"),
    category: str | None = Query(None, description="Filter by category"),
    search: str | None = Query(None, description="Search in subject or from_address"),
    current_user: User = Depends(require_role(Role.SALES_REP, Role.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """List emails with pagination and filtering."""
    query = select(EmailRequest)
    count_query = select(func.count(EmailRequest.id))

    conditions = []
    if status:
        conditions.append(EmailRequest.status == status)
    if review_status:
        conditions.append(EmailRequest.review_status == review_status)
    if category:
        conditions.append(EmailRequest.category == category)
    if search:
        search_term = f"%{search}%"
        conditions.append(
            or_(
                EmailRequest.subject.ilike(search_term),
                EmailRequest.from_address.ilike(search_term),
            )
        )

    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    offset = (page - 1) * page_size
    query = query.order_by(EmailRequest.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    emails = result.scalars().all()

    return {
        "items": [_email_to_dict(e) for e in emails],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/{email_id}")
async def get_email(
    email_id: int,
    current_user: User = Depends(require_role(Role.SALES_REP, Role.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Get email detail by ID."""
    result = await db.execute(
        select(EmailRequest).where(EmailRequest.id == email_id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException(f"Email with id {email_id} not found")

    return _email_to_dict(email, include_body=True)


@router.post("/manual", status_code=201)
async def create_manual_email(
    data: dict,
    current_user: User = Depends(require_role(Role.SALES_REP, Role.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Manual email entry. Creates an email request and triggers parsing."""
    from_address = data.get("from_address")
    subject = data.get("subject")
    body_text = data.get("body_text")

    if not from_address or not body_text:
        raise BadRequestException("from_address and body_text are required")

    email = EmailRequest(
        message_id=f"manual-{uuid.uuid4().hex}",
        from_address=from_address,
        subject=subject or "(No Subject)",
        body_text=body_text,
        status="new",
        received_at=datetime.now(timezone.utc),
        assigned_to=current_user.id,
    )
    db.add(email)
    await db.flush()
    await db.refresh(email)

    # Parse with Claude
    try:
        from app.services.claude_parser import parse_email
        body = body_text or ""
        parsed = await parse_email(body)

        if parsed:
            import json
            email.parsed_data = json.dumps(parsed)
            email.language = parsed.get("language")
            email.status = "parsed"

            from app.services.email_classifier import classify_email
            classification = classify_email(subject or "", body)
            email.category = classification.get("category")
            email.category_confidence = classification.get("confidence")
            email.price_sensitivity = classification.get("price_sensitivity")

            if email.category_confidence and email.category_confidence < 0.75:
                email.review_status = "pending_review"
            else:
                email.review_status = "approved"

            await db.flush()
            await db.refresh(email)
    except Exception as e:
        email.status = "error"
        email.error_message = str(e)[:500]
        await db.flush()
        await db.refresh(email)

    return _email_to_dict(email, include_body=True)


@router.post("/poll", status_code=200)
async def poll_emails(
    current_user: User = Depends(require_role(Role.SALES_REP, Role.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Trigger email fetch from Microsoft Graph API."""
    # TODO: Implement Graph API polling via service layer
    # fetched = await graph_service.fetch_new_emails()
    return {"message": "Email polling triggered", "fetched_count": 0}


@router.post("/{email_id}/reparse", status_code=200)
async def reparse_email(
    email_id: int,
    current_user: User = Depends(require_role(Role.SALES_REP, Role.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Re-parse an email with Claude."""
    result = await db.execute(
        select(EmailRequest).where(EmailRequest.id == email_id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException(f"Email with id {email_id} not found")

    # Reset status
    email.status = "new"
    email.parsed_data = None
    email.error_message = None
    await db.flush()

    # Parse with Claude
    try:
        from app.services.claude_parser import parse_email
        body = email.body_text or email.body_html or ""
        parsed = await parse_email(body)

        if parsed:
            import json
            email.parsed_data = json.dumps(parsed)
            email.language = parsed.get("language")
            email.status = "parsed"

            # Classify
            from app.services.email_classifier import classify_email
            classification = classify_email(email.subject or "", body)
            email.category = classification.get("category")
            email.category_confidence = classification.get("confidence")
            email.price_sensitivity = classification.get("price_sensitivity")

            # Review gate
            if email.category_confidence and email.category_confidence < 0.75:
                email.review_status = "pending_review"
            else:
                email.review_status = "approved"
        else:
            email.status = "error"
            email.error_message = "Claude parse returned empty"
    except Exception as e:
        email.status = "error"
        email.error_message = str(e)[:500]

    await db.flush()

    return {"message": f"Email {email_id} parsed", "status": email.status}


@router.get("/{email_id}/matches")
async def get_email_matches(
    email_id: int,
    current_user: User = Depends(require_role(Role.SALES_REP, Role.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Get part match results for a parsed email."""
    result = await db.execute(
        select(EmailRequest).where(EmailRequest.id == email_id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException(f"Email with id {email_id} not found")

    parsed_data = None
    if email.parsed_data:
        try:
            parsed_data = json.loads(email.parsed_data)
        except json.JSONDecodeError:
            parsed_data = None

    return {
        "email_id": email_id,
        "status": email.status,
        "parsed_data": parsed_data,
        "matches": [],  # TODO: Populate from part matching service
    }


@router.patch("/{email_id}/review")
async def review_email(
    email_id: int,
    data: dict,
    current_user: User = Depends(require_role(Role.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject an email (sales_manager only)."""
    action = data.get("action")
    if action not in ("approve", "reject"):
        raise BadRequestException("action must be 'approve' or 'reject'")

    result = await db.execute(
        select(EmailRequest).where(EmailRequest.id == email_id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException(f"Email with id {email_id} not found")

    if email.review_status != "pending_review":
        raise BadRequestException(
            f"Email is not pending review (current status: {email.review_status})"
        )

    email.review_status = "approved" if action == "approve" else "rejected"
    email.reviewed_by = current_user.id
    await db.flush()

    return _email_to_dict(email)


def _email_to_dict(email: EmailRequest, include_body: bool = False) -> dict:
    """Convert EmailRequest to a dictionary response."""
    data = {
        "id": email.id,
        "customer_id": email.customer_id,
        "message_id": email.message_id,
        "from_address": email.from_address,
        "subject": email.subject,
        "language": email.language,
        "received_at": email.received_at.isoformat() if email.received_at else None,
        "status": email.status,
        "error_message": email.error_message,
        "category": email.category,
        "category_confidence": email.category_confidence,
        "price_sensitivity": email.price_sensitivity,
        "review_status": email.review_status,
        "assigned_to": email.assigned_to,
        "reviewed_by": email.reviewed_by,
        "created_at": email.created_at.isoformat() if email.created_at else None,
    }
    if include_body:
        data["body_text"] = email.body_text
        data["body_html"] = email.body_html
        data["parsed_data"] = (
            json.loads(email.parsed_data) if email.parsed_data else None
        )
    return data
