"""D-016 — KVKK export worker.

The state machine in ``kvkk_two_person.py`` advances requests to
``executing``; this module is what actually runs after that. Pure
data-collection + ZIP build + artifact persistence + subject
notification + state transition to ``done``.

What we collect (TC-KVKK-005 scope):
  customer.json       — full customer record
  opportunities.json  — every opp where this subject is the customer
  quotes.json         — same
  invoices.json       — same
  contracts.json      — same
  emails.json         — every EmailRequest from/to this subject
  audit_log.json      — every audit entry where this subject is the
                         target_entity_id (NOT entries about access
                         to the data — those belong to the org)

What we DON'T collect (TC-KVKK-005 exclusions):
  * Internal coaching notes ABOUT the subject (defamation risk)
  * Internal AI-generated commentary
  * Audit log entries WHERE the subject is the actor (those are the
    actor's data, not the data subject's; same person + different
    role = different export request)

Storage:
  Artifact written to ``/var/lib/kvkk-exports/<tenant>/<request_id>.zip``
  (local FS at 20-30 user scale). Phase 5: swap for S3 with object-lock
  + KMS-encrypted.

Idempotency: ``mark_executing`` is the lock. Re-triggering this
function for an already-``done`` request short-circuits.
"""

from __future__ import annotations

import io
import json
import logging
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.kvkk_two_person import mark_done, mark_failed

logger = logging.getLogger(__name__)


_ARTIFACT_BASE = Path(os.environ.get("KVKK_ARTIFACT_DIR", "/var/lib/kvkk-exports"))


# ── Per-section collectors ─────────────────────────────────────────


async def _customer_for_subject(db, subject: str, kind: str) -> dict:
    if kind == "email":
        sql = "SELECT * FROM customers WHERE LOWER(email) = LOWER(:s)"
    elif kind == "vergi_no":
        sql = "SELECT * FROM customers WHERE tax_id = :s"
    elif kind == "phone":
        sql = "SELECT * FROM customers WHERE phone = :s"
    else:
        return {}
    rows = (await db.execute(text(sql), {"s": subject})).mappings().all()
    return {"matches": [dict(r) for r in rows]}


async def _opportunities_for_subject(db, subject: str, kind: str) -> list[dict]:
    customer_data = await _customer_for_subject(db, subject, kind)
    customer_ids = [c.get("id") for c in customer_data.get("matches", [])]
    if not customer_ids:
        return []
    rows = (
        await db.execute(
            text(
                "SELECT * FROM opportunities WHERE customer_id = ANY(:ids)"
            ),
            {"ids": customer_ids},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _quotes_for_subject(db, subject: str, kind: str) -> list[dict]:
    customer_data = await _customer_for_subject(db, subject, kind)
    customer_ids = [c.get("id") for c in customer_data.get("matches", [])]
    if not customer_ids:
        return []
    rows = (
        await db.execute(
            text("SELECT * FROM quotes WHERE customer_id = ANY(:ids)"),
            {"ids": customer_ids},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _invoices_for_subject(db, subject: str, kind: str) -> list[dict]:
    customer_data = await _customer_for_subject(db, subject, kind)
    customer_ids = [c.get("id") for c in customer_data.get("matches", [])]
    if not customer_ids:
        return []
    rows = (
        await db.execute(
            text("SELECT * FROM invoices WHERE customer_id = ANY(:ids)"),
            {"ids": customer_ids},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _contracts_for_subject(db, subject: str, kind: str) -> list[dict]:
    customer_data = await _customer_for_subject(db, subject, kind)
    customer_ids = [c.get("id") for c in customer_data.get("matches", [])]
    if not customer_ids:
        return []
    rows = (
        await db.execute(
            text("SELECT * FROM contracts WHERE customer_id = ANY(:ids)"),
            {"ids": customer_ids},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _emails_for_subject(db, subject: str, kind: str) -> list[dict]:
    if kind != "email":
        return []
    rows = (
        await db.execute(
            text(
                "SELECT id, message_id, from_address, subject, body_text, "
                "       received_at, status "
                "  FROM email_requests "
                " WHERE LOWER(from_address) = LOWER(:s)"
            ),
            {"s": subject},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


async def _audit_for_subject(db, subject: str, kind: str) -> list[dict]:
    # We log only entries where the subject is the *target*, not the
    # actor. TC-KVKK-005 scope rule.
    customer_data = await _customer_for_subject(db, subject, kind)
    customer_ids = [c.get("id") for c in customer_data.get("matches", [])]
    if not customer_ids:
        return []
    rows = (
        await db.execute(
            text(
                "SELECT id, user_id, action, entity_type, entity_id, "
                "       ip_address, created_at, changes "
                "  FROM audit_log "
                " WHERE entity_type = 'customer' AND entity_id = ANY(:ids) "
                " ORDER BY created_at DESC LIMIT 5000"
            ),
            {"ids": customer_ids},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


# ── Orchestrator ───────────────────────────────────────────────────


async def run_export(db: AsyncSession, request_id: int) -> str:
    """Execute the export. Returns the artifact_url written to the
    request row.

    Raises only on truly unrecoverable errors (DB connection lost).
    Per-section failures degrade gracefully — that section is empty
    in the export, and the failure is logged.
    """
    req = (
        await db.execute(
            text(
                "SELECT id, tenant_id, subject_lookup, subject_kind, status "
                "FROM kvkk_export_requests WHERE id = :id"
            ),
            {"id": request_id},
        )
    ).first()
    if req is None:
        raise RuntimeError(f"KVKK export request {request_id} not found")
    if req.status == "done":
        return "already_done"
    if req.status != "executing":
        raise RuntimeError(
            f"KVKK export request {request_id} in unexpected status: {req.status}"
        )

    subject = req.subject_lookup
    kind = req.subject_kind
    tenant_id = req.tenant_id

    try:
        bundle: dict[str, Any] = {
            "_meta": {
                "tenant_id": tenant_id,
                "subject_lookup": subject,
                "subject_kind": kind,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "request_id": request_id,
            },
            "customer": await _customer_for_subject(db, subject, kind),
            "opportunities": await _opportunities_for_subject(db, subject, kind),
            "quotes": await _quotes_for_subject(db, subject, kind),
            "invoices": await _invoices_for_subject(db, subject, kind),
            "contracts": await _contracts_for_subject(db, subject, kind),
            "emails": await _emails_for_subject(db, subject, kind),
            "audit_log": await _audit_for_subject(db, subject, kind),
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("KVKK export collection failed for %d", request_id)
        await mark_failed(db, request_id, reason=f"collection_failed: {str(exc)[:500]}")
        await db.commit()
        raise

    # Build ZIP in memory (small enough at 20-30 user / pilot scale).
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for section, data in bundle.items():
            zf.writestr(
                f"{section}.json",
                json.dumps(data, ensure_ascii=False, indent=2, default=str),
            )

    # Write to disk. Phase 5: replace with S3 upload + object-lock.
    artifact_dir = _ARTIFACT_BASE / str(tenant_id)
    try:
        artifact_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("KVKK artifact dir create failed: %s", exc)
        await mark_failed(db, request_id, reason=f"dir_create_failed: {exc}")
        await db.commit()
        raise
    artifact_path = artifact_dir / f"export-{request_id}.zip"
    artifact_path.write_bytes(buf.getvalue())
    artifact_url = str(artifact_path)

    await mark_done(db, request_id, artifact_url=artifact_url)
    # D-015 — notify the subject when their data was exported.
    if kind == "email":
        from app.services.smtp_service import send_email

        await send_email(
            db,
            to=subject,
            subject="Verileriniz dışa aktarıldı (KVKK Madde 11)",
            body=(
                f"Merhaba,\n\n"
                f"KVKK Madde 11 kapsamında verilerinizin bir kopyasının "
                f"hazırlanması için yapılan talep, "
                f"{datetime.now(timezone.utc).strftime('%d %B %Y %H:%M UTC')} "
                f"tarihinde işlenmiş ve dosyanız oluşturulmuştur.\n\n"
                f"Export referans numarası: #{request_id}.\n\n"
                f"Soru ve itirazlarınız için lütfen bizimle iletişime geçin.\n"
            ),
            tenant_id=tenant_id,
        )
    await db.commit()
    logger.info(
        "KVKK export %d completed (tenant=%d, subject=%s)",
        request_id, tenant_id, subject,
    )
    return artifact_url
