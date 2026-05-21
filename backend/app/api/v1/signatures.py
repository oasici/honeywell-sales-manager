"""E-Signature API — document signing workflow with public signing endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundException
from app.core.rate_limit import enforce_signing_rate_limit
from app.models.contract import Contract
from app.models.invoice import Invoice
from app.models.quote import Quote
from app.models.signature import SignatureRequest
from app.models.user import User
from app.services.tenant_context import assert_same_tenant, scoped_for_user
from app.schemas.common import ItemsResponse, MessageResponse
from app.schemas.round16_aggregates import (
    SignatureRequestResponse,
    SigningPageResponse,
)

router = APIRouter(prefix="/signatures", tags=["E-Signatures"])

VALID_DOCUMENT_TYPES = {"quote", "contract", "invoice"}


def _require_esign():
    """Dependency: reject if FEATURE_ESIGN is off."""
    if not settings.FEATURE_ESIGN:
        raise HTTPException(status_code=404, detail="Not found")


# ── Pydantic Schemas ──


class SignatureRequestCreate(BaseModel):
    document_type: str = Field(min_length=1, max_length=20)
    document_id: int
    signer_email: EmailStr
    signer_name: Optional[str] = Field(default=None, max_length=200)


class SignatureSubmit(BaseModel):
    signature_data: str = Field(min_length=1, max_length=500_000)
    signer_name: Optional[str] = Field(default=None, max_length=200)


# ── Helpers ──


def _sig_to_dict(sig: SignatureRequest) -> dict:
    return {
        "id": sig.id,
        "tenant_id": getattr(sig, "tenant_id", None),
        "document_type": sig.document_type,
        "document_id": sig.document_id,
        "signer_email": sig.signer_email,
        "signer_name": sig.signer_name,
        "status": sig.status,
        "token": sig.token,
        "signed_at": sig.signed_at.isoformat() if sig.signed_at else None,
        "viewed_at": sig.viewed_at.isoformat() if sig.viewed_at else None,
        "expires_at": sig.expires_at.isoformat() if sig.expires_at else None,
        "ip_address": sig.ip_address,
        "created_by": sig.created_by,
        "created_at": sig.created_at.isoformat() if sig.created_at else None,
        "updated_at": sig.updated_at.isoformat() if sig.updated_at else None,
    }


async def _get_sig_or_404(token: str, db: AsyncSession) -> SignatureRequest:
    result = await db.execute(
        select(SignatureRequest).where(SignatureRequest.token == token)
    )
    sig = result.scalar_one_or_none()
    if not sig:
        raise HTTPException(status_code=404, detail="Imza talebi bulunamadi")
    return sig


async def _load_document_summary(
    document_type: str,
    document_id: int,
    db: AsyncSession,
    *,
    current_user: User | None = None,
    sig: SignatureRequest | None = None,
) -> dict:
    """Return a minimal summary of the referenced document.

    Round-4 R4-TEN-9: when ``current_user`` is provided (authenticated
    callers) we enforce same-tenant access on the loaded doc. When
    ``sig`` is provided (public sign callback path) we additionally
    require the SignatureRequest's tenant_id to match the doc's
    tenant_id, preventing a leaked signing token from referencing a
    foreign-tenant document.
    """
    if document_type == "quote":
        result = await db.execute(select(Quote).where(Quote.id == document_id))
        doc = result.scalar_one_or_none()
        if not doc:
            return {"document_type": "quote", "document_id": document_id, "found": False}
        if current_user is not None:
            assert_same_tenant(doc, current_user, exception_cls=NotFoundException)
        if sig is not None:
            _assert_sig_doc_tenant_match(sig, doc)
        return {
            "document_type": "quote",
            "document_id": document_id,
            "found": True,
            "status": doc.status,
            "customer_id": doc.customer_id,
        }

    if document_type == "contract":
        result = await db.execute(select(Contract).where(Contract.id == document_id))
        doc = result.scalar_one_or_none()
        if not doc:
            return {"document_type": "contract", "document_id": document_id, "found": False}
        if current_user is not None:
            assert_same_tenant(doc, current_user, exception_cls=NotFoundException)
        if sig is not None:
            _assert_sig_doc_tenant_match(sig, doc)
        return {
            "document_type": "contract",
            "document_id": document_id,
            "found": True,
            "status": doc.status,
            "customer_id": doc.customer_id,
            "title": doc.title,
        }

    if document_type == "invoice":
        result = await db.execute(select(Invoice).where(Invoice.id == document_id))
        doc = result.scalar_one_or_none()
        if not doc:
            return {"document_type": "invoice", "document_id": document_id, "found": False}
        if current_user is not None:
            assert_same_tenant(doc, current_user, exception_cls=NotFoundException)
        if sig is not None:
            _assert_sig_doc_tenant_match(sig, doc)
        return {
            "document_type": "invoice",
            "document_id": document_id,
            "found": True,
            "status": doc.status,
            "customer_id": doc.customer_id,
            "invoice_number": doc.invoice_number,
            "grand_total": doc.grand_total,
            "currency": doc.currency,
        }

    raise HTTPException(status_code=400, detail="Unknown document type")


def _assert_sig_doc_tenant_match(sig: SignatureRequest, doc) -> None:
    """Round-4 R4-TEN-9: public sign callback guard.

    Both the SignatureRequest and the underlying document must belong
    to the same tenant. If either side has tenant_id == None we treat
    it as same-tenant (single-tenant deployment) — same tolerant
    semantics as ``is_cross_tenant``. A mismatch maps to 404 so a
    leaked token can't disclose the existence of a foreign-tenant doc.
    """
    sig_tenant = getattr(sig, "tenant_id", None)
    doc_tenant = getattr(doc, "tenant_id", None)
    if sig_tenant is None or doc_tenant is None:
        return
    if sig_tenant != doc_tenant:
        raise NotFoundException("Not found")


async def _apply_document_status_update(
    document_type: str,
    document_id: int,
    db: AsyncSession,
    *,
    current_user: User | None = None,
    sig: SignatureRequest | None = None,
) -> None:
    """Update the referenced document's status after a successful signature.

    Round-4 R4-TEN-9: same tenant guard as ``_load_document_summary``.
    A signed callback must not be able to mutate a foreign-tenant doc
    even if the signer used the right token (either the token leaked
    or two tenants happened to mint colliding document ids).
    """
    now = datetime.now(timezone.utc)

    if document_type == "quote":
        result = await db.execute(select(Quote).where(Quote.id == document_id))
        doc = result.scalar_one_or_none()
        if doc:
            if current_user is not None:
                assert_same_tenant(doc, current_user, exception_cls=NotFoundException)
            if sig is not None:
                _assert_sig_doc_tenant_match(sig, doc)
            doc.status = "accepted"

    elif document_type == "contract":
        result = await db.execute(select(Contract).where(Contract.id == document_id))
        doc = result.scalar_one_or_none()
        if doc:
            if current_user is not None:
                assert_same_tenant(doc, current_user, exception_cls=NotFoundException)
            if sig is not None:
                _assert_sig_doc_tenant_match(sig, doc)
            doc.status = "active"
            doc.signed_at = now

    elif document_type == "invoice":
        result = await db.execute(select(Invoice).where(Invoice.id == document_id))
        doc = result.scalar_one_or_none()
        if doc:
            if current_user is not None:
                assert_same_tenant(doc, current_user, exception_cls=NotFoundException)
            if sig is not None:
                _assert_sig_doc_tenant_match(sig, doc)
            doc.status = "paid"


# ── Authenticated Endpoints ──


@router.post("/request", status_code=201, response_model=MessageResponse)
async def create_signature_request(
    body: SignatureRequestCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_esign),
):
    """Create a new e-signature request for a document."""
    if body.document_type not in VALID_DOCUMENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Gecersiz belge tipi. Kabul edilenler: {', '.join(VALID_DOCUMENT_TYPES)}",
        )

    # Round-4 R4-TEN-9: load + tenant-check the referenced doc before
    # we even create a SignatureRequest pointing at it. Otherwise a
    # caller could create a pending sig referencing any document id.
    model_map = {"quote": Quote, "contract": Contract, "invoice": Invoice}
    model = model_map[body.document_type]
    doc_result = await db.execute(select(model).where(model.id == body.document_id))
    target_doc = doc_result.scalar_one_or_none()
    if target_doc is None:
        raise NotFoundException("Not found")
    assert_same_tenant(target_doc, current_user, exception_cls=NotFoundException)

    sig = SignatureRequest(
        document_type=body.document_type,
        document_id=body.document_id,
        signer_email=body.signer_email,
        signer_name=body.signer_name,
        created_by=current_user.id,
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    db.add(sig)
    await db.commit()
    await db.refresh(sig)
    return {
        "message": "Imza talebi olusturuldu",
        "id": sig.id,
        "token": sig.token,
        "signer_email": sig.signer_email,
        "expires_at": sig.expires_at.isoformat(),
    }


@router.get("/", response_model=ItemsResponse)
async def list_signature_requests(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_esign),
):
    """List signature requests created by the current user."""
    from sqlalchemy import func

    base_stmt = (
        select(SignatureRequest)
        .where(SignatureRequest.created_by == current_user.id)
    )
    # Round-4 R4-TEN-9: defence-in-depth — even within the user's own
    # rows, narrow to their tenant in case a row was created before
    # tenant_id existed.
    base_stmt = scoped_for_user(
        base_stmt, current_user, column=SignatureRequest.tenant_id
    )
    query = base_stmt.order_by(SignatureRequest.created_at.desc())

    count_result = await db.execute(
        select(func.count()).select_from(query.subquery())
    )
    total = count_result.scalar_one()

    result = await db.execute(query.offset(skip).limit(limit))
    sigs = result.scalars().all()

    return {
        "items": [_sig_to_dict(s) for s in sigs],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{sig_id}", response_model=SignatureRequestResponse)
async def get_signature_request(
    sig_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_esign),
):
    """Get signature request detail."""
    result = await db.execute(
        select(SignatureRequest).where(SignatureRequest.id == sig_id)
    )
    sig = result.scalar_one_or_none()
    if not sig:
        raise HTTPException(status_code=404, detail="Imza talebi bulunamadi")
    assert_same_tenant(sig, current_user, exception_cls=NotFoundException)
    return _sig_to_dict(sig)


@router.delete("/{sig_id}", response_model=MessageResponse)
async def cancel_signature_request(
    sig_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_esign),
):
    """Cancel a pending signature request."""
    result = await db.execute(
        select(SignatureRequest).where(SignatureRequest.id == sig_id)
    )
    sig = result.scalar_one_or_none()
    if not sig:
        raise HTTPException(status_code=404, detail="Imza talebi bulunamadi")
    assert_same_tenant(sig, current_user, exception_cls=NotFoundException)
    if sig.status != "pending":
        raise HTTPException(
            status_code=400,
            detail="Yalnizca bekleyen imza talepleri iptal edilebilir",
        )

    await db.delete(sig)
    await db.commit()
    return {"message": "Imza talebi iptal edildi", "id": sig_id}


# ── Public Endpoints (no auth) ──


@router.get("/sign/{token}", response_model=SigningPageResponse)
async def get_signing_page(
    token: str,
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_esign),
    _rl=Depends(enforce_signing_rate_limit),
):
    """Return document summary for the public signing page (no auth required)."""
    sig = await _get_sig_or_404(token, db)

    if sig.status in ("signed", "declined", "expired"):
        raise HTTPException(
            status_code=410,
            detail=f"Bu imza talebi artik gecerli degil: {sig.status}",
        )

    now = datetime.now(timezone.utc)
    if sig.expires_at < now:
        sig.status = "expired"
        await db.commit()
        raise HTTPException(status_code=410, detail="Imza talebi suresi dolmus")

    # Record first view
    if sig.status == "pending" and not sig.viewed_at:
        sig.viewed_at = now
        sig.status = "viewed"
        await db.commit()

    document_summary = await _load_document_summary(
        sig.document_type, sig.document_id, db, sig=sig,
    )

    return {
        "id": sig.id,
        "document_type": sig.document_type,
        "document_id": sig.document_id,
        "signer_email": sig.signer_email,
        "signer_name": sig.signer_name,
        "status": sig.status,
        "expires_at": sig.expires_at.isoformat(),
        "document": document_summary,
    }


@router.post("/sign/{token}", response_model=MessageResponse)
async def submit_signature(
    token: str,
    body: SignatureSubmit,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_esign),
    _rl=Depends(enforce_signing_rate_limit),
):
    """Submit a signature for the given token (no auth required)."""
    sig = await _get_sig_or_404(token, db)

    if sig.status == "signed":
        raise HTTPException(status_code=409, detail="Bu belge zaten imzalandi")
    if sig.status in ("declined", "expired"):
        raise HTTPException(
            status_code=410,
            detail=f"Bu imza talebi artik gecerli degil: {sig.status}",
        )

    now = datetime.now(timezone.utc)
    if sig.expires_at < now:
        sig.status = "expired"
        await db.commit()
        raise HTTPException(status_code=410, detail="Imza talebi suresi dolmus")

    client_ip = request.client.host if request.client else None

    sig.status = "signed"
    sig.signed_at = now
    sig.signature_data = body.signature_data
    sig.ip_address = client_ip
    if body.signer_name:
        sig.signer_name = body.signer_name

    await _apply_document_status_update(
        sig.document_type, sig.document_id, db, sig=sig,
    )
    await db.commit()

    return {
        "message": "Belge basariyla imzalandi",
        "id": sig.id,
        "signed_at": sig.signed_at.isoformat(),
    }


@router.post("/sign/{token}/decline", response_model=MessageResponse)
async def decline_signature(
    token: str,
    db: AsyncSession = Depends(get_db),
    _flag=Depends(_require_esign),
    _rl=Depends(enforce_signing_rate_limit),
):
    """Decline a signature request (no auth required)."""
    sig = await _get_sig_or_404(token, db)

    if sig.status in ("signed", "declined", "expired"):
        raise HTTPException(
            status_code=410,
            detail=f"Bu imza talebi artik gecerli degil: {sig.status}",
        )

    sig.status = "declined"
    await db.commit()
    return {"message": "Imza talebi reddedildi", "id": sig.id}
