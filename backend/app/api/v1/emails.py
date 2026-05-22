import json
import math

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.email_request import EmailRequest
from app.models.enums import ReviewStatus, UserRole
from app.models.opportunity import Opportunity
from app.models.user import User
from app.schemas.email_request import EmailResponse, ManualEmailCreate
from app.core.event_bus import event_bus
from app.services.activity_logger import log_activity
from app.services.email_processing_service import EmailProcessingService
from app.services.notification_service import create_notification
from app.services.tenant_context import assert_same_tenant
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.round16_aggregates import EmailMatchesResponse


def _assert_email_same_tenant(email: EmailRequest, user: User) -> None:
    """R4-TEN-23 — enforce tenant boundary on EmailRequest detail loads.

    EmailRequest carries its own ``tenant_id`` after the round-4
    migration. Pre-migration rows have ``tenant_id == None`` and pass
    through ``assert_same_tenant`` unchanged, so we keep backwards
    compatibility while still locking down newly stamped rows.

    Cross-tenant probes surface as 404 (NotFoundException) so the API
    never leaks which email IDs exist in foreign tenants.
    """
    try:
        assert_same_tenant(email, user, exception_cls=NotFoundException)
    except NotFoundException:
        raise NotFoundException("E-posta bulunamadi")


class EmailReviewRequest(BaseModel):
    action: str = Field(..., pattern="^(approve|reject)$")


class EmailOpportunityLinkBody(BaseModel):
    """Link or unlink an inbound email to a v2 opportunity (same customer when both set)."""

    opportunity_id: int | None = None

router = APIRouter(prefix="/emails", tags=["Emails"])


def _check_email_ownership(email: EmailRequest, user: User) -> None:
    """Raise 403 if non-manager user doesn't own the email."""
    if user.role != UserRole.SALES_MANAGER.value and email.assigned_to != user.id:
        raise ForbiddenException("Bu e-postaya erisim yetkiniz yok")


@router.get("/", response_model=PaginatedResponse[EmailResponse])
async def list_emails(
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(50, ge=1, le=100),
    is_read: bool | None = Query(None, description="Filter by read status"),
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
    # Ownership scoping: non-managers see only emails assigned to them
    if current_user.role != UserRole.SALES_MANAGER.value:
        conditions.append(EmailRequest.assigned_to == current_user.id)
    if is_read is not None:
        conditions.append(EmailRequest.is_read == is_read)
    if status:
        conditions.append(EmailRequest.status == status)
    if review_status:
        conditions.append(EmailRequest.review_status == review_status)
    if category:
        conditions.append(EmailRequest.category == category)
    if search:
        safe_search = search.replace("%", "\\%").replace("_", "\\_")
        search_term = f"%{safe_search}%"
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


# Round-15 N15-API-1: response_model exempt (returns non-JSON: file/redirect/stream)
@router.get("/training-data", status_code=200)
async def get_training_data(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    model_used: str | None = Query(None),
    field: str | None = Query(None, description="Filter by corrected field"),
    format: str = Query("json", description="json or jsonl"),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Export AI training data with pagination and filtering."""
    from app.models.ai_training_data import AITrainingData
    from fastapi.responses import PlainTextResponse

    query = select(AITrainingData).order_by(AITrainingData.created_at.desc())
    count_query = select(func.count(AITrainingData.id))

    if model_used:
        query = query.where(AITrainingData.model_used == model_used)
        count_query = count_query.where(AITrainingData.model_used == model_used)
    if field:
        query = query.where(AITrainingData.correction_fields.contains(field))
        count_query = count_query.where(AITrainingData.correction_fields.contains(field))

    total = (await db.execute(count_query)).scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(query.offset(offset).limit(page_size))
    entries = result.scalars().all()

    def _safe_json(s: str | None) -> dict | None:
        if not s:
            return None
        try:
            return json.loads(s)
        except (json.JSONDecodeError, TypeError):
            return None

    items = [
        {
            "id": e.id,
            "email_id": e.email_id,
            "original_parse": _safe_json(e.original_parse),
            "corrected_parse": _safe_json(e.corrected_parse),
            "correction_fields": e.correction_fields.split(",") if e.correction_fields else [],
            "model_used": e.model_used,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]

    if format == "jsonl":
        lines = "\n".join(json.dumps(item, ensure_ascii=False) for item in items)
        return PlainTextResponse(content=lines, media_type="application/jsonl")

    # Round-5 Phase 7 — canonical pagination envelope. ``count`` and
    # ``data`` are kept additively for any in-flight consumers.
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total > 0 else 0,
        # Additive legacy keys.
        "count": total,
        "data": items,
    }


@router.get("/{email_id}", response_model=EmailResponse)
async def get_email(
    email_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Get email detail by ID. Non-managers can only see emails assigned to them."""
    result = await db.execute(
        select(EmailRequest).where(EmailRequest.id == email_id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException("E-posta bulunamadi")
    _assert_email_same_tenant(email, current_user)

    # Ownership check: non-managers can only access emails assigned to them
    if current_user.role != UserRole.SALES_MANAGER.value and email.assigned_to != current_user.id:
        raise ForbiddenException("Bu e-postaya erisim yetkiniz yok")

    return _email_to_dict(email, include_body=True)


@router.post("/manual", status_code=201, response_model=EmailResponse)
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
    # R4-TEN-23: stamp tenant_id on the freshly-created row so later
    # detail loads can enforce same-tenant scope. Single-tenant
    # deployments leave current_user.tenant_id == None which keeps the
    # column nullable as before.
    if getattr(current_user, "tenant_id", None) is not None and email.tenant_id is None:
        email.tenant_id = current_user.tenant_id
        await db.flush()

    # Best-effort notification
    try:
        await create_notification(
            db, user_id=current_user.id, type="new_email",
            title="Yeni email eklendi",
            message=f"{data.from_address}: {data.subject[:80]}",
            entity_type="email", entity_id=email.id,
        )
    except Exception:
        pass

    return _email_to_dict(email, include_body=True)


@router.post("/poll", status_code=200, response_model=MessageResponse)
async def poll_emails(
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Fetch last 14 days of emails via IMAP. Max 2 polls per day."""
    import asyncio
    import logging as _log
    from datetime import datetime, timezone as tz
    from app.models.setting import Setting

    _logger = _log.getLogger(__name__)

    # ── Daily poll limit: 2/day (atomic update to prevent race condition) ──
    from sqlalchemy import text as sa_text

    today_str = datetime.now(tz.utc).strftime("%Y-%m-%d")
    poll_counter_result = await db.execute(
        select(Setting).where(Setting.key == "poll_daily_counter").with_for_update()
    )
    poll_counter_setting = poll_counter_result.scalar_one_or_none()
    poll_count_today = 0
    if poll_counter_setting and poll_counter_setting.value:
        parts = poll_counter_setting.value.split(":")
        if len(parts) == 2 and parts[0] == today_str:
            poll_count_today = int(parts[1])

    if poll_count_today >= 2:
        raise BadRequestException("Gunluk email kontrol limiti doldu (max 2/gun). Yarin tekrar deneyin.")

    # Increment counter immediately (atomic)
    new_count = f"{today_str}:{poll_count_today + 1}"
    if poll_counter_setting:
        poll_counter_setting.value = new_count
    else:
        db.add(Setting(key="poll_daily_counter", value=new_count))
    await db.flush()

    # ── Load IMAP credentials ──
    result = await db.execute(
        select(Setting).where(
            Setting.key.in_(["email_address", "email_password", "imap_host", "imap_port"])
        )
    )
    stored = {s.key: s.value for s in result.scalars().all()}

    email_addr = stored.get("email_address", "")
    encrypted_pass = stored.get("email_password", "")
    imap_host = stored.get("imap_host", "")
    imap_port = int(stored.get("imap_port") or "993")

    if not email_addr or not encrypted_pass:
        raise BadRequestException(
            "Email bilgileri ayarlanmamis. Ayarlar sayfasindan email baglantisi kurun."
        )

    from app.api.v1.settings import _decrypt_password, _detect_provider
    email_pass = _decrypt_password(encrypted_pass)

    detected_h, detected_p, _, _ = _detect_provider(email_addr)
    if not imap_host or imap_host in {"", "outlook.office365.com"}:
        imap_host = detected_h
        imap_port = detected_p

    # ── Fetch emails in thread (non-blocking) ──
    try:
        raw_emails = await asyncio.to_thread(
            _fetch_emails_via_imap, imap_host, imap_port, email_addr, email_pass, 0
        )
    except Exception as exc:
        _logger.error("IMAP fetch failed: %s", exc)
        raise BadRequestException("Email sunucusuna baglanilamadi. Ayarlarinizi kontrol edin.")

    if not raw_emails:
        return {"message": "Yeni email bulunamadi (son 14 gun)", "fetched_count": 0}

    # ── Process fetched emails ──
    fetched_count = 0
    service = EmailProcessingService(db)
    from app.core.config import settings as cfg

    for item in raw_emails:
        try:
            # Skip internal emails
            from_domain = item["from_addr"].rsplit("@", 1)[-1].lower() if "@" in item["from_addr"] else ""
            if from_domain in cfg.internal_domains_list:
                continue

            # Skip duplicates
            existing = await db.execute(
                select(EmailRequest).where(EmailRequest.message_id == item["message_id"])
            )
            if existing.scalar_one_or_none():
                continue

            # Create with IMAP SEEN status as is_read
            # R4-TEN-23: stamp tenant_id from the polling user so the row
            # is scoped to a tenant from creation; downstream detail
            # endpoints enforce ``assert_same_tenant``.
            # Round-17 — persist parsed attachment payload + auth verdict.
            # Untrusted senders (anything except pass) flip review_status
            # so the auto-quote loop refuses to act until a human signs off.
            attachments_payload = item.get("attachments") or []
            attachments_json = None
            if attachments_payload:
                import json as _json
                try:
                    attachments_json = _json.dumps(attachments_payload, ensure_ascii=False)
                except Exception:
                    attachments_json = None

            sender_auth = item.get("sender_auth_status") or "none"
            initial_review_status = (
                None if sender_auth == "pass" else "pending_review"
            )

            email = EmailRequest(
                message_id=item["message_id"],
                from_address=item["from_addr"],
                subject=item["subject"] or "(Konu yok)",
                body_text=item["body"],
                body_html=item.get("html_body") or None,
                status="new",
                is_read=item.get("is_read", False),
                received_at=datetime.now(tz.utc),
                assigned_to=current_user.id,
                tenant_id=getattr(current_user, "tenant_id", None),
                attachments_json=attachments_json,
                sender_auth_status=sender_auth,
                review_status=initial_review_status,
            )
            db.add(email)
            await db.flush()
            await db.refresh(email)

            # Parse
            try:
                await service.process_email(email.id)
            except Exception as parse_exc:
                _logger.warning("Parse failed for email %d: %s", email.id, parse_exc)

            fetched_count += 1
        except Exception as exc:
            _logger.warning("Email processing error: %s", exc)
            continue


    # Best-effort notification for fetched emails
    if fetched_count > 0:
        try:
            await create_notification(
                db, user_id=current_user.id, type="new_email",
                title=f"{fetched_count} yeni email alindi",
                message="IMAP uzerinden yeni emailler yuklendi.",
                entity_type="email", entity_id=None,
            )
        except Exception:
            pass

    return {
        "message": f"{fetched_count} yeni email alindi (son 14 gun)",
        "fetched_count": fetched_count,
    }


@router.get("/{email_id}/thread", response_model=PaginatedResponse[EmailResponse])
async def get_email_thread(
    email_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Get all emails in the same thread, ordered chronologically."""
    result = await db.execute(
        select(EmailRequest).where(EmailRequest.id == email_id)
    )
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException("E-posta bulunamadi")
    _assert_email_same_tenant(email, current_user)
    _check_email_ownership(email, current_user)

    # Round-5 Phase 7 — canonical envelope. ``thread_id`` is kept as
    # an extra field, and ``emails`` is preserved additively so the
    # SPA can read either ``items`` or ``emails`` mid-rollout.
    if not email.thread_id:
        single = [_email_to_dict(email)]
        return {
            "items": single,
            "total": 1,
            "page": 1,
            "page_size": 1,
            "pages": 1,
            "thread_id": None,
            "emails": single,
        }

    thread_result = await db.execute(
        select(EmailRequest)
        .where(EmailRequest.thread_id == email.thread_id)
        .order_by(EmailRequest.created_at.asc())
    )
    thread_emails = thread_result.scalars().all()
    items = [_email_to_dict(e) for e in thread_emails]
    total = len(items)

    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total if total > 0 else 1,
        "pages": 1 if total > 0 else 0,
        "thread_id": email.thread_id,
        "emails": items,
    }


@router.patch("/{email_id}/opportunity", status_code=200, response_model=EmailResponse)
async def link_email_to_opportunity(
    email_id: int,
    body: EmailOpportunityLinkBody,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Set `email_requests.opportunity_id` for v2 timeline (requires FEATURE_V2_BOARD)."""
    if not settings.FEATURE_V2_BOARD:
        raise HTTPException(status_code=404, detail="Not found")

    result = await db.execute(select(EmailRequest).where(EmailRequest.id == email_id))
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException("E-posta bulunamadi")
    _assert_email_same_tenant(email, current_user)
    _check_email_ownership(email, current_user)

    if body.opportunity_id is None:
        email.opportunity_id = None
        await db.flush()
        return _email_to_dict(email)

    opp = (
        await db.execute(select(Opportunity).where(Opportunity.id == body.opportunity_id))
    ).scalar_one_or_none()
    if not opp:
        raise NotFoundException("Firsat bulunamadi")
    # R4-TEN-23: prevent linking an email to a foreign-tenant opportunity.
    # Cross-tenant lookups collapse to 404 indistinguishable from "doesn't
    # exist" so this endpoint can't be used as an enumeration oracle.
    try:
        assert_same_tenant(opp, current_user, exception_cls=NotFoundException)
    except NotFoundException:
        raise NotFoundException("Firsat bulunamadi")

    if current_user.role == UserRole.SALES_REP.value and opp.owner_id != current_user.id:
        raise ForbiddenException("Bu firsata baglama yetkiniz yok")

    if (
        email.customer_id is not None
        and opp.customer_id is not None
        and int(email.customer_id) != int(opp.customer_id)
    ):
        raise BadRequestException("E-posta ve firsat ayni musteriye ait olmali")

    email.opportunity_id = int(body.opportunity_id)
    await db.flush()
    await db.refresh(email)
    return _email_to_dict(email)


@router.patch("/{email_id}/read", status_code=200, response_model=MessageResponse)
async def mark_email_read(
    email_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark an email as read."""
    result = await db.execute(select(EmailRequest).where(EmailRequest.id == email_id))
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException("E-posta bulunamadi")
    _assert_email_same_tenant(email, current_user)
    _check_email_ownership(email, current_user)
    email.is_read = True
    await db.flush()
    return {"message": "OK"}


@router.post("/{email_id}/reparse", status_code=200, response_model=EmailResponse)
async def reparse_email(
    email_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Re-parse an email with Claude. Max 2 parses per day."""
    from datetime import datetime, timezone as tz
    from app.models.setting import Setting

    result = await db.execute(select(EmailRequest).where(EmailRequest.id == email_id))
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException("E-posta bulunamadi")
    _assert_email_same_tenant(email, current_user)
    _check_email_ownership(email, current_user)

    # Daily parse limit: 2/day (atomic lock to prevent race condition)
    today_str = datetime.now(tz.utc).strftime("%Y-%m-%d")
    parse_counter_result = await db.execute(
        select(Setting).where(Setting.key == "reparse_daily_counter").with_for_update()
    )
    parse_counter_setting = parse_counter_result.scalar_one_or_none()
    parse_count_today = 0
    if parse_counter_setting and parse_counter_setting.value:
        parts = parse_counter_setting.value.split(":")
        if len(parts) == 2 and parts[0] == today_str:
            parse_count_today = int(parts[1])

    if parse_count_today >= 2:
        raise BadRequestException("Gunluk yeniden ayristirma limiti doldu (max 2/gun)")

    # Increment atomically before processing
    new_count = f"{today_str}:{parse_count_today + 1}"
    if parse_counter_setting:
        parse_counter_setting.value = new_count
    else:
        db.add(Setting(key="reparse_daily_counter", value=new_count))
    await db.flush()

    service = EmailProcessingService(db)
    email = await service.process_email(email_id)
    email.last_parsed_at = datetime.now(tz.utc)
    await db.flush()
    await db.refresh(email)

    return _email_to_dict(email, include_body=True)


class CorrectParseRequest(BaseModel):
    parsed_data: dict


@router.patch("/{email_id}/correct-parse", status_code=200, response_model=MessageResponse)
async def correct_parse(
    email_id: int,
    body: CorrectParseRequest,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Save a user correction to email parse data. Stores both original and corrected for training."""
    from app.models.ai_training_data import AITrainingData

    result = await db.execute(select(EmailRequest).where(EmailRequest.id == email_id))
    email = result.scalar_one_or_none()
    if not email:
        raise NotFoundException("E-posta bulunamadi")
    _assert_email_same_tenant(email, current_user)
    _check_email_ownership(email, current_user)

    original_parse = email.parsed_data or "{}"
    corrected_data = body.parsed_data
    if not corrected_data:
        raise BadRequestException("parsed_data alani gereklidir")

    # Detect which fields changed
    try:
        original = json.loads(original_parse)
    except (json.JSONDecodeError, TypeError):
        original = {}

    changed_fields = []
    for key in ["customer_name", "customer_company", "parts", "category", "is_spare_part_request"]:
        if key in corrected_data and corrected_data.get(key) != original.get(key):
            changed_fields.append(key)

    if not changed_fields:
        return {"message": "Degisiklik bulunamadi", "changed_fields": []}

    # Save training data
    training_entry = AITrainingData(
        email_id=email_id,
        original_parse=original_parse,
        corrected_parse=json.dumps(corrected_data, ensure_ascii=False),
        correction_fields=",".join(changed_fields),
        model_used="claude" if email.status == "parsed" else "regex",
        created_by=current_user.id,
    )
    db.add(training_entry)

    # Update email's parsed_data
    email.parsed_data = json.dumps(corrected_data, ensure_ascii=False)
    await db.flush()

    return {
        "message": f"Duzeltme kaydedildi ({len(changed_fields)} alan)",
        "changed_fields": changed_fields,
    }


@router.get("/{email_id}/matches", response_model=EmailMatchesResponse)
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
        raise NotFoundException("E-posta bulunamadi")
    _assert_email_same_tenant(email, current_user)
    _check_email_ownership(email, current_user)

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


@router.patch("/{email_id}/review", response_model=EmailResponse)
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
        raise NotFoundException("E-posta bulunamadi")
    # R4-TEN-23: managers from tenant A must not be able to review/approve
    # tenant B emails. Cross-tenant collapses to 404.
    _assert_email_same_tenant(email, current_user)

    if email.review_status != ReviewStatus.PENDING_REVIEW.value:
        raise BadRequestException(
            f"E-posta inceleme beklemede degil (mevcut durum: {email.review_status})"
        )

    email.review_status = ReviewStatus.APPROVED.value if action == "approve" else ReviewStatus.REJECTED.value
    email.reviewed_by = current_user.id

    # On manual approval, auto-create customer + draft quote
    if action == "approve" and email.parsed_data:
        try:
            parsed = json.loads(email.parsed_data)
            service = EmailProcessingService(db)
            await service._auto_create_customer(email, parsed)
            if parsed.get("parts") and parsed.get("confidence", 0) >= 0.5:
                await service._auto_create_draft_quote(email, parsed)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Auto-create on approval failed: %s", exc)

    await db.flush()

    await log_activity(
        db, activity_type="email_parsed", entity_type="email", entity_id=email.id,
        opportunity_id=email.opportunity_id, customer_id=email.customer_id,
        user_id=current_user.id,
        summary=f"Email incelendi ({action}): {email.subject[:80] if email.subject else ''}",
        source_ref=f"email_review:{email.message_id or email.id}:{action}",
    )
    await event_bus.publish("email.parsed", {
        "email_id": email.id, "action": action,
        "customer_id": email.customer_id, "category": email.category,
    })

    # Best-effort notification to assignee
    if email.assigned_to and email.assigned_to != current_user.id:
        try:
            status_label = "onaylandi" if action == "approve" else "reddedildi"
            await create_notification(
                db, user_id=email.assigned_to, type="email_reviewed",
                title=f"Email {status_label}",
                message=f'"{email.subject[:60]}" incelendi.',
                entity_type="email", entity_id=email.id,
            )
        except Exception:
            pass

    return _email_to_dict(email)


def _fetch_emails_via_imap(
    imap_host: str, imap_port: int, email_addr: str, email_pass: str, last_uid: int
) -> list[dict]:
    """Synchronous IMAP fetch — runs in a thread via asyncio.to_thread.

    Fetches last 14 days of emails (both read and unread).
    Returns is_read status from IMAP SEEN flag.
    """
    import imaplib
    import ssl
    import email as email_lib
    import re
    from email.header import decode_header
    from datetime import datetime, timedelta

    # Round-17 — explicit TLS context with certificate + hostname
    # verification. The default ``IMAP4_SSL`` constructor uses
    # ``ssl.create_default_context()`` *only when* no ssl_context is
    # passed; we pass one explicitly so the policy is loud + auditable
    # and future overrides (cert pinning, allowed-cipher list) can
    # land in one place.
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = True
    ssl_ctx.verify_mode = ssl.CERT_REQUIRED
    imap = imaplib.IMAP4_SSL(imap_host, imap_port, ssl_context=ssl_ctx, timeout=30)
    imap.login(email_addr, email_pass)
    imap.select("INBOX", readonly=True)

    # Always fetch last 14 days (both SEEN and UNSEEN)
    since_date = (datetime.now() - timedelta(days=14)).strftime("%d-%b-%Y")
    status, data = imap.search(None, f'(SINCE "{since_date}")')

    if status != "OK" or not data[0]:
        imap.logout()
        return []

    # Limit to latest 30 emails to avoid timeout
    msg_ids = data[0].split()[-30:]
    results: list[dict] = []

    for msg_id in msg_ids:
        try:
            # Fetch FLAGS first to get SEEN status
            flag_status, flag_data = imap.fetch(msg_id, "(FLAGS)")
            is_seen = False
            if flag_status == "OK" and flag_data[0]:
                flags_line = flag_data[0] if isinstance(flag_data[0], bytes) else b""
                is_seen = b"\\Seen" in flags_line

            # Then fetch email body
            fetch_status, msg_data = imap.fetch(msg_id, "(BODY.PEEK[])")

            if fetch_status != "OK" or not msg_data[0]:
                continue

            raw_email = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw_email)

            # Decode subject
            subject = ""
            for part, charset in decode_header(msg.get("Subject", "")):
                subject += part.decode(charset or "utf-8", errors="replace") if isinstance(part, bytes) else part

            # Parse from address safely
            from email.utils import parseaddr
            from_raw = msg.get("From", "")
            _, from_addr = parseaddr(from_raw)
            if not from_addr:
                from_addr = from_raw

            message_id = msg.get("Message-ID", f"imap-{msg_id.decode() if isinstance(msg_id, bytes) else msg_id}")

            # Round-17 email hardening — walk MIME tree to collect:
            #   1. plain text body (preferred for LLM input)
            #   2. HTML body (sanitized + table-preserved as fallback)
            #   3. attachments (Excel / CSV / PDF for parts extraction)
            body_text = ""
            body_html = ""
            attachments: list[tuple[str, bytes]] = []

            if msg.is_multipart():
                for part in msg.walk():
                    ct = part.get_content_type()
                    disposition = (part.get("Content-Disposition") or "").lower()
                    is_attachment = "attachment" in disposition or bool(part.get_filename())
                    if is_attachment:
                        fname_raw = part.get_filename() or ""
                        # decode_header handles RFC 2047-encoded filenames
                        # (very common with Turkish letters in source ERPs).
                        fname = ""
                        for piece, cset in decode_header(fname_raw):
                            fname += (
                                piece.decode(cset or "utf-8", errors="replace")
                                if isinstance(piece, bytes)
                                else piece
                            )
                        try:
                            payload = part.get_payload(decode=True)
                        except Exception:
                            payload = None
                        if payload and fname:
                            attachments.append((fname, payload))
                        continue
                    if ct == "text/plain" and not body_text:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body_text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
                    elif ct == "text/html" and not body_html:
                        payload = part.get_payload(decode=True)
                        if payload:
                            body_html = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            else:
                payload = msg.get_payload(decode=True)
                if payload:
                    cs = msg.get_content_charset() or "utf-8"
                    if msg.get_content_type() == "text/html":
                        body_html = payload.decode(cs, errors="replace")
                    else:
                        body_text = payload.decode(cs, errors="replace")

            # Convert HTML body to plain text with table preservation
            # (Round-17 — replaces the legacy 3-line regex strip).
            sanitized_html = ""
            if body_html:
                from app.services.email_html_cleaner import sanitize_and_extract_text

                sanitized_html, html_plain = sanitize_and_extract_text(body_html)
                if not body_text:
                    body_text = html_plain

            body = body_text
            if not body and not attachments:
                continue

            # Parse attachments now so the LLM context is ready when
            # the downstream EmailProcessingService picks it up.
            parsed_attachments: list[dict] = []
            if attachments:
                from app.services.email_attachment_parser import (
                    extract_rows_as_parts,
                    parse_attachments,
                )

                for pa in parse_attachments(attachments):
                    entry = {
                        "filename": pa.filename,
                        "content_type": pa.content_type,
                        "size_bytes": pa.size_bytes,
                        "sheet_count": pa.sheet_count,
                        "page_count": pa.page_count,
                        "text": pa.text,
                        "heuristic_parts": extract_rows_as_parts(pa.rows) if pa.rows else [],
                        "error": pa.error,
                    }
                    parsed_attachments.append(entry)

            # Round-17 — resolve SPF/DKIM/DMARC verdict from raw message.
            from app.services.email_auth_verifier import resolve_sender_auth

            sender_auth = resolve_sender_auth(raw_email)

            results.append({
                "uid": 0,
                "message_id": message_id,
                "from_addr": from_addr,
                "subject": subject,
                "body": body,
                "html_body": sanitized_html or body_html,
                "is_read": is_seen,
                "attachments": parsed_attachments,
                "sender_auth_status": sender_auth,
            })
        except Exception as exc:
            import logging as _imap_log
            _imap_log.getLogger(__name__).warning("IMAP message parse error for %s: %s", msg_id, exc)
            continue

    imap.logout()
    return results


def _email_to_dict(email: EmailRequest, include_body: bool = False) -> dict:
    """Convert EmailRequest to a dictionary response."""
    data = {
        "id": email.id,
        # R5-API-4 — round-trip tenant_id and dedupe metadata so the
        # SPA's "duplicate of" link can render and so multi-tenant
        # analytics can group emails by tenant.
        "tenant_id": getattr(email, "tenant_id", None),
        "is_duplicate": getattr(email, "is_duplicate", False),
        "duplicate_of_id": getattr(email, "duplicate_of_id", None),
        "customer_id": email.customer_id,
        "opportunity_id": getattr(email, "opportunity_id", None),
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
        "thread_id": getattr(email, "thread_id", None),
        "in_reply_to": getattr(email, "in_reply_to", None),
        "is_read": getattr(email, "is_read", False),
        # AI triage outputs — these are computed by the email parsing
        # pipeline and stored on the row but were never serialised,
        # so the inbox couldn't show priority badges, sentiment dots,
        # or the AI's reason for the triage decision.
        "priority": getattr(email, "priority", None),
        "triage_reason": getattr(email, "triage_reason", None),
        "sentiment": getattr(email, "sentiment", None),
        "sentiment_score": getattr(email, "sentiment_score", None),
        "data_classification": getattr(email, "data_classification", None),
        "last_parsed_at": email.last_parsed_at.isoformat() if getattr(email, "last_parsed_at", None) else None,
        # Round-17 — SPF/DKIM/DMARC verdict surfaces in the list view
        # so the SPA can show "verified sender" / "needs review"
        # badges without re-loading the full detail.
        "sender_auth_status": getattr(email, "sender_auth_status", None),
        "created_at": email.created_at.isoformat() if email.created_at else None,
    }
    if include_body:
        data["body_text"] = email.body_text
        data["body_html"] = email.body_html
        data["parsed_data"] = (
            json.loads(email.parsed_data) if email.parsed_data else None
        )
        # Round-17 — return parsed attachments as structured list so
        # the SPA can render chips with row counts + per-file open
        # actions. JSON-decode-on-read keeps the DB column TEXT.
        att_raw = getattr(email, "attachments_json", None)
        if att_raw:
            try:
                data["attachments_json"] = json.loads(att_raw)
            except (json.JSONDecodeError, TypeError):
                data["attachments_json"] = None
    # Field-level masking (R4-PERM-1).
    from app.services.field_permission_service import apply_request_perms
    return apply_request_perms(data, "email")
