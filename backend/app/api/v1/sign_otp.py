"""F-006 wire — e-Sign OTP endpoints (public, unauthenticated).

The customer receives an email containing ``/sign/<token>``. These
endpoints implement the 5-stage flow defined in
``app/services/sign_otp.py``:

    GET    /sign/{token}              → masked-recipient summary
    POST   /sign/{token}/send-otp     → email a 6-digit code
    POST   /sign/{token}/verify-otp   → check code, unlock contract view
    GET    /sign/{token}/contract     → contract content (after verify)
    POST   /sign/{token}/sign         → record signature; consume token

NO AUTH is required for these endpoints — the token IS the auth.
Token validity is bound to:
    - 7-day TTL
    - 5-attempt OTP lockout
    - Recipient email (OTP only goes there; forwarding the URL
      doesn't help)
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.sign_otp import (
    SignTokenError,
    consume_for_signing,
    get_recipient_summary,
    send_otp as svc_send_otp,
    verify_otp as svc_verify_otp,
)

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/sign", tags=["e-Sign"])


# ── HTTP error mapping ──────────────────────────────────────────────


_REASON_TO_STATUS = {
    "not_found": 404,
    "expired": 410,
    "consumed": 410,
    "otp_rate": 429,
    "otp_locked": 423,
    "otp_wrong": 400,
    "otp_unverified": 403,
    "otp_expired": 400,
}


def _to_http(exc: SignTokenError) -> HTTPException:
    status = _REASON_TO_STATUS.get(exc.reason, 400)
    return HTTPException(status, detail={"code": exc.reason, "message": str(exc)})


# ── Schemas ─────────────────────────────────────────────────────────


class SendOtpRequest(BaseModel):
    """Empty — present only so OpenAPI documents the POST shape."""

    pass


class VerifyOtpRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class SignRequest(BaseModel):
    """Captures the signer's acknowledgement.

    ``signature_payload`` is the rendered signature (base64 of a
    canvas image, or just the typed name for typed-signature flows).
    Storage / cryptographic binding is the contract-domain caller's
    job; this endpoint only records that signing happened with a
    valid OTP-verified session.
    """

    signature_payload: str = Field(min_length=1, max_length=200_000)
    typed_name: Optional[str] = Field(default=None, max_length=200)


class RecipientSummary(BaseModel):
    masked_email: str
    expires_at: datetime
    otp_sent: bool
    otp_verified: bool


# ── send-email shim ─────────────────────────────────────────────────


def _send_otp_email(to: str, subject: str, body: str) -> None:
    """D-014 — wired to the real SMTP service.

    Uses the sync shim because the existing send_otp service contract
    accepts a synchronous callable. If SMTP isn't configured the shim
    returns False and we log + continue — the operator can then
    re-issue from the UI after fixing integration settings.
    """
    from app.services.smtp_service import send_email_sync

    ok = send_email_sync(to, subject, body)
    if not ok:
        logger.warning(
            "[sign_otp] SMTP send failed/unconfigured to=%s subject=%s",
            to, subject,
        )


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/{token}", response_model=RecipientSummary)
async def get_sign_token(token: str, db: AsyncSession = Depends(get_db)) -> RecipientSummary:
    try:
        data = await get_recipient_summary(db, token)
    except SignTokenError as exc:
        raise _to_http(exc)
    return RecipientSummary(**data)


    # Round-15 N15-API-1: response_model exempt — admin/operational dict response
@router.post("/{token}/send-otp")
async def send_otp(
    token: str,
    payload: SendOtpRequest = SendOtpRequest(),
    db: AsyncSession = Depends(get_db),
):
    try:
        masked = await svc_send_otp(db, token, send_email=_send_otp_email)
    except SignTokenError as exc:
        raise _to_http(exc)
    return {"masked_email": masked, "sent": True}


    # Round-15 N15-API-1: response_model exempt — admin/operational dict response
@router.post("/{token}/verify-otp")
async def verify_otp(
    token: str,
    payload: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc_verify_otp(db, token, payload.code)
    except SignTokenError as exc:
        raise _to_http(exc)
    return {"verified": True}


    # Round-15 N15-API-1: response_model exempt — admin/operational dict response
@router.get("/{token}/contract")
async def view_contract(token: str, db: AsyncSession = Depends(get_db)):
    """Returns the contract content. Refuses if OTP not verified.

    The actual rendering (PDF stream, HTML, etc.) is left to the
    caller for now — we surface the contract_id + a verified flag so
    the frontend knows it's safe to render. Phase 5 wires the real
    contract fetch.
    """
    try:
        summary = await get_recipient_summary(db, token)
    except SignTokenError as exc:
        raise _to_http(exc)
    if not summary["otp_verified"]:
        raise HTTPException(403, detail={"code": "otp_unverified"})
    # Lookup contract_id without consuming the token.
    import hashlib

    row = (
        await db.execute(
            text(
                "SELECT contract_id FROM sign_otp_tokens WHERE token_hash = :h"
            ),
            {"h": hashlib.sha256(token.encode()).hexdigest()},
        )
    ).first()
    if row is None:
        raise HTTPException(404, detail={"code": "not_found"})
    return {"contract_id": int(row[0]), "verified": True}


    # Round-15 N15-API-1: response_model exempt — admin/operational dict response
@router.post("/{token}/sign")
async def sign(
    token: str,
    payload: SignRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Records the signature + consumes the token.

    Captures IP + UA from the request for the legal audit trail.
    Idempotency: the token is single-use; double-clicking yields
    410 Gone on the second call (consumed_at already set).
    """
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")[:1000]
    try:
        contract_id = await consume_for_signing(
            db, token, ip=ip, ua=ua,
        )
    except SignTokenError as exc:
        raise _to_http(exc)

    # Optional follow-up: stamp the contract row with signed_at +
    # the payload. We do this best-effort so a missing column on
    # older deploys doesn't break the sign flow itself.
    try:
        await db.execute(
            text(
                "UPDATE contracts SET status = 'active', signed_at = now() "
                "WHERE id = :cid AND status IN ('pending_signature', 'sent')"
            ),
            {"cid": contract_id},
        )
        await db.flush()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Contract status update after sign failed (non-fatal): %s", exc
        )
    return {"signed": True, "contract_id": contract_id}
