import json
import math

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.email_request import EmailRequest
from app.models.enums import ReviewStatus, UserRole
from app.models.user import User
from app.schemas.email_request import ManualEmailCreate
from app.services.email_processing_service import EmailProcessingService


class EmailReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")

router = APIRouter(prefix="/emails", tags=["Emails"])


@router.get("/")
async def list_emails(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = Query(None, description="Filter by processing status"),
    review_status: str | None = Query(None, description="Filter by review status"),
    category: str | None = Query(None, description="Filter by category"),
    search: str | None = Query(None, description="Search in subject or from_address"),
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
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
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Get email detail by ID."""
    result = await db.execute(
        select(EmailRequest).where(EmailRequest.id == email_id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException(f"{email_id} numarali e-posta bulunamadi")

    return _email_to_dict(email, include_body=True)


@router.post("/manual", status_code=201)
async def create_manual_email(
    data: ManualEmailCreate,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Manual email entry. Creates an email request and triggers parsing."""
    service = EmailProcessingService(db)
    email = await service.create_manual_email(
        from_address=data.from_address,
        subject=data.subject,
        body_text=data.body_text,
        assigned_to=current_user.id,
    )

    return _email_to_dict(email, include_body=True)


@router.post("/poll", status_code=200)
async def poll_emails(
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Fetch new emails via IMAP using stored credentials."""
    import imaplib
    import email as email_lib
    from email.header import decode_header
    from app.models.setting import Setting

    # Load stored IMAP credentials
    result = await db.execute(
        select(Setting).where(
            Setting.key.in_(["email_address", "email_password", "imap_host", "imap_port"])
        )
    )
    stored = {s.key: s.value for s in result.scalars().all()}

    email_addr = stored.get("email_address", "")
    encrypted_pass = stored.get("email_password", "")
    imap_host = stored.get("imap_host", "")
    imap_port = int(stored.get("imap_port", "993"))

    if not email_addr or not encrypted_pass:
        raise BadRequestException(
            "Email bilgileri ayarlanmamis. Ayarlar sayfasindan email baglantisi kurun."
        )

    # Decrypt password
    from app.api.v1.settings import _decrypt_password, _detect_provider
    email_pass = _decrypt_password(encrypted_pass)

    # Auto-detect provider if needed
    detected_h, detected_p, _, _ = _detect_provider(email_addr)
    default_hosts = {"", "outlook.office365.com"}
    if not imap_host or imap_host in default_hosts:
        imap_host = detected_h
        imap_port = detected_p

    # Get last poll timestamp to only fetch new emails
    ts_result = await db.execute(
        select(Setting).where(Setting.key == "last_imap_poll_uid")
    )
    last_uid_setting = ts_result.scalar_one_or_none()
    last_uid = int(last_uid_setting.value) if last_uid_setting and last_uid_setting.value else 0

    try:
        imap = imaplib.IMAP4_SSL(imap_host, imap_port)
        imap.login(email_addr, email_pass)
        imap.select("INBOX", readonly=True)

        # Search for unseen emails (or all if first poll)
        search_criteria = "UNSEEN" if last_uid == 0 else f"UID {last_uid + 1}:*"
        if last_uid > 0:
            status, data = imap.uid("search", None, f"UID {last_uid + 1}:*")
        else:
            status, data = imap.search(None, "UNSEEN")

        if status != "OK" or not data[0]:
            imap.logout()
            return {"message": "Yeni email bulunamadi", "fetched_count": 0}

        msg_ids = data[0].split()
        # Limit to latest 20 to avoid overload
        msg_ids = msg_ids[-20:]

        fetched_count = 0
        max_uid = last_uid
        service = EmailProcessingService(db)

        for msg_id in msg_ids:
            try:
                if last_uid > 0:
                    fetch_status, msg_data = imap.uid("fetch", msg_id, "(RFC822)")
                else:
                    fetch_status, msg_data = imap.fetch(msg_id, "(RFC822)")

                if fetch_status != "OK" or not msg_data[0]:
                    continue

                raw_email = msg_data[0][1]
                msg = email_lib.message_from_bytes(raw_email)

                # Parse UID for tracking
                if last_uid > 0:
                    uid_val = int(msg_id)
                    if uid_val > max_uid:
                        max_uid = uid_val

                # Decode subject
                subject_parts = decode_header(msg.get("Subject", ""))
                subject = ""
                for part, charset in subject_parts:
                    if isinstance(part, bytes):
                        subject += part.decode(charset or "utf-8", errors="replace")
                    else:
                        subject += part

                # Parse from address
                from_raw = msg.get("From", "")
                from_parts = decode_header(from_raw)
                from_str = ""
                for part, charset in from_parts:
                    if isinstance(part, bytes):
                        from_str += part.decode(charset or "utf-8", errors="replace")
                    else:
                        from_str += part

                # Extract email address from "Name <email>" format
                from_addr = from_str
                if "<" in from_str and ">" in from_str:
                    from_addr = from_str.split("<")[1].split(">")[0]

                # Skip internal emails
                from app.core.config import settings as cfg
                from_domain = from_addr.rsplit("@", 1)[-1].lower() if "@" in from_addr else ""
                if from_domain in cfg.internal_domains_list:
                    continue

                # Skip if already exists (by message_id)
                message_id = msg.get("Message-ID", f"imap-{msg_id.decode()}")
                existing = await db.execute(
                    select(EmailRequest).where(EmailRequest.message_id == message_id)
                )
                if existing.scalar_one_or_none():
                    continue

                # Extract body text
                body_text = ""
                body_html = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        content_type = part.get_content_type()
                        if content_type == "text/plain" and not body_text:
                            payload = part.get_payload(decode=True)
                            if payload:
                                charset = part.get_content_charset() or "utf-8"
                                body_text = payload.decode(charset, errors="replace")
                        elif content_type == "text/html" and not body_html:
                            payload = part.get_payload(decode=True)
                            if payload:
                                charset = part.get_content_charset() or "utf-8"
                                body_html = payload.decode(charset, errors="replace")
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        charset = msg.get_content_charset() or "utf-8"
                        if msg.get_content_type() == "text/html":
                            body_html = payload.decode(charset, errors="replace")
                        else:
                            body_text = payload.decode(charset, errors="replace")

                if not body_text and not body_html:
                    continue

                # Create email request and process
                email_req = await service.create_manual_email(
                    from_address=from_addr,
                    subject=subject or "(Konu yok)",
                    body_text=body_text or body_html,
                    assigned_to=current_user.id,
                )
                fetched_count += 1

            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Email parse hatasi: %s", exc)
                continue

        imap.logout()

        # Update last UID
        if max_uid > last_uid:
            if last_uid_setting:
                last_uid_setting.value = str(max_uid)
            else:
                db.add(Setting(key="last_imap_poll_uid", value=str(max_uid)))

        return {
            "message": f"{fetched_count} yeni email alindi",
            "fetched_count": fetched_count,
        }

    except imaplib.IMAP4.error as e:
        raise BadRequestException(f"IMAP giris hatasi: {str(e)}")
    except Exception as e:
        raise BadRequestException(f"Email cekme hatasi: {str(e)}")


@router.post("/{email_id}/reparse", status_code=200)
async def reparse_email(
    email_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Re-parse an email with Claude."""
    service = EmailProcessingService(db)
    email = await service.process_email(email_id)

    return {"message": f"Email {email_id} parsed", "status": email.status}


@router.get("/{email_id}/matches")
async def get_email_matches(
    email_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Get part match results for a parsed email."""
    result = await db.execute(
        select(EmailRequest).where(EmailRequest.id == email_id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException(f"{email_id} numarali e-posta bulunamadi")

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
    data: EmailReviewRequest,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Approve or reject an email (sales_manager only)."""
    action = data.action

    result = await db.execute(
        select(EmailRequest).where(EmailRequest.id == email_id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException(f"{email_id} numarali e-posta bulunamadi")

    if email.review_status != ReviewStatus.PENDING_REVIEW.value:
        raise BadRequestException(
            f"E-posta inceleme beklemede degil (mevcut durum: {email.review_status})"
        )

    email.review_status = ReviewStatus.APPROVED.value if action == "approve" else ReviewStatus.REJECTED.value
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
