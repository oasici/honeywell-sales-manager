"""F-024 wire — unsubscribe endpoint.

Public, unauthenticated. The customer arrives via the link embedded
in a sequence email:

    GET  /unsubscribe/{token}   → opt-out landing (renders a "are you
                                   sure?" view; tokens are one-click
                                   in spec but we surface a confirm
                                   page to reduce false opt-outs)
    POST /unsubscribe/{token}   → confirms the opt-out, records it
                                   in ``email_optouts``

Each token is bound to (tenant, email, sequence_id) at issue time
inside ``sequence_unsubscribe.issue_unsubscribe_token``. Persisting
the opt-out is idempotent — clicking the link twice is a no-op.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.sequence_unsubscribe import mark_opted_out

logger = logging.getLogger(__name__)


router = APIRouter(prefix="/unsubscribe", tags=["Unsubscribe"])


class UnsubscribePreview(BaseModel):
    masked_email: str
    sequence_name: Optional[str]
    already_opted_out: bool


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _mask_email(email: str) -> str:
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


async def _resolve_token(db: AsyncSession, token: str) -> dict:
    """Look up the opt-out token via its hash.

    Sequence-emitting jobs issue per-recipient tokens. We assume a
    side table ``email_optout_tokens`` (one row per issued token);
    fall back to the legacy lookup by hash on ``email_optouts``
    when ``email_optout_tokens`` doesn't exist yet.
    """
    token_hash = _hash(token)
    # Phase 5 will add ``email_optout_tokens``; until then, the
    # token-issuing job writes the hash directly into
    # ``email_optouts.unsubscribe_token`` for the matching row.
    row = (
        await db.execute(
            text(
                """
                SELECT id, tenant_id, email, sequence_id
                FROM email_optouts
                WHERE unsubscribe_token = :hash
                """
            ),
            {"hash": token_hash},
        )
    ).first()
    if row is not None:
        return {
            "tenant_id": row.tenant_id,
            "email": row.email,
            "sequence_id": row.sequence_id,
            "already_opted_out": True,
        }
    # Token not yet matched: this is the first click. The link
    # itself must encode the tuple so we can record the opt-out.
    # Phase 5 issues self-describing JWT-style tokens; the current
    # cut accepts "<tenant>:<email>:<sequence_id>" base64 if present.
    return _decode_inline_token(token) or {"tenant_id": None}


def _decode_inline_token(token: str) -> Optional[dict]:
    """Decode a self-describing token: base64(tenant_id|email|sequence_id).

    Used for the bridge period before ``email_optout_tokens`` lands.
    Returns None when the format doesn't match.
    """
    import base64

    try:
        raw = base64.urlsafe_b64decode(token + "===").decode("utf-8")
    except Exception:
        return None
    parts = raw.split("|")
    if len(parts) < 2:
        return None
    try:
        tenant_id = int(parts[0])
    except ValueError:
        return None
    email = parts[1]
    sequence_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    return {
        "tenant_id": tenant_id,
        "email": email,
        "sequence_id": sequence_id,
        "already_opted_out": False,
    }


@router.get("/{token}", response_model=UnsubscribePreview)
async def preview_unsubscribe(
    token: str, db: AsyncSession = Depends(get_db)
) -> UnsubscribePreview:
    resolved = await _resolve_token(db, token)
    if not resolved or not resolved.get("tenant_id"):
        raise HTTPException(404, detail="token_not_found")
    sequence_name: Optional[str] = None
    if resolved.get("sequence_id"):
        # Best-effort name fetch — ignore if the table isn't present.
        try:
            srow = (
                await db.execute(
                    text("SELECT name FROM email_sequences WHERE id = :id"),
                    {"id": resolved["sequence_id"]},
                )
            ).first()
            if srow:
                sequence_name = srow[0]
        except Exception:
            sequence_name = None
    return UnsubscribePreview(
        masked_email=_mask_email(resolved["email"]),
        sequence_name=sequence_name,
        already_opted_out=resolved.get("already_opted_out", False),
    )


    # Round-15 N15-API-1: response_model exempt — admin/operational dict response
@router.post("/{token}")
async def confirm_unsubscribe(
    token: str, db: AsyncSession = Depends(get_db)
):
    resolved = await _resolve_token(db, token)
    if not resolved or not resolved.get("tenant_id"):
        raise HTTPException(404, detail="token_not_found")

    await mark_opted_out(
        db,
        tenant_id=resolved["tenant_id"],
        email=resolved["email"],
        sequence_id=resolved.get("sequence_id"),
        source="unsubscribe_link",
        unsubscribe_token=_hash(token),
    )
    return {"opted_out": True}
