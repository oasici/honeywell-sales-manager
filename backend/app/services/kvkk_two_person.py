"""F-023 — KVKK export with two-person rule.

KVKK Article 11 grants data subjects the right to obtain a copy of
their data. The export pulls every record referencing that subject
across customers, leads, opportunities, quotes, contracts,
invoices, email_requests — a near-total PII bundle.

Pre-Round-19 any single Operations user could execute this export
unilaterally. That's an insider-attack hole: one compromised ops
account = full PII dump of any subject. The audit demanded a
two-person rule:

    1. Operator A files a *request* with the subject identifier
       (email / vergi_no / phone).
    2. Operator B (≠ A) reviews and approves.
    3. Only after approval does the export job actually run.
    4. The subject is notified ("Your data was requested on Y,
       approved by Z, exported on X").

Implementation: ``kvkk_export_requests`` table tracks the state
machine. The CHECK constraint
``approved_by IS NULL OR approved_by != requested_by`` enforces
"different person" at the DB level — even if the API layer is
bypassed, the row can't land in ``approved`` state with one user.

This module is the service layer. The HTTP endpoints
(``POST /kvkk-export/requests``, ``POST /kvkk-export/requests/<id>/approve``,
``POST /kvkk-export/requests/<id>/execute``) call these helpers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


SUBJECT_KINDS = ("email", "vergi_no", "phone")


class TwoPersonViolation(Exception):
    """Raised when the same user attempts both request + approve."""


class StateError(Exception):
    """Raised when the transition is forbidden by the current state."""


@dataclass
class ExportRequest:
    id: int
    tenant_id: int
    subject_lookup: str
    subject_kind: str
    status: str            # requested | approved | executing | done | rejected | failed
    requested_by: int
    requested_at: datetime
    approved_by: Optional[int]
    approved_at: Optional[datetime]
    executed_at: Optional[datetime]
    artifact_url: Optional[str]
    reject_reason: Optional[str]


async def create_request(
    db: AsyncSession,
    *,
    tenant_id: int,
    subject_lookup: str,
    subject_kind: str,
    requested_by: int,
) -> ExportRequest:
    """File a new KVKK export request. Returns the persisted row."""
    if subject_kind not in SUBJECT_KINDS:
        raise StateError(
            f"subject_kind must be one of {SUBJECT_KINDS}, got {subject_kind!r}"
        )
    row = (
        await db.execute(
            text(
                """
                INSERT INTO kvkk_export_requests
                  (tenant_id, subject_lookup, subject_kind, requested_by, status)
                VALUES
                  (:tid, :lookup, :kind, :by, 'requested')
                RETURNING id, requested_at
                """
            ),
            {
                "tid": tenant_id,
                "lookup": subject_lookup,
                "kind": subject_kind,
                "by": requested_by,
            },
        )
    ).first()
    await db.flush()
    logger.info(
        "KVKK export request #%d filed (tenant=%d, by=%d, kind=%s)",
        row[0], tenant_id, requested_by, subject_kind,
    )
    return ExportRequest(
        id=int(row[0]),
        tenant_id=tenant_id,
        subject_lookup=subject_lookup,
        subject_kind=subject_kind,
        status="requested",
        requested_by=requested_by,
        requested_at=row[1].replace(tzinfo=timezone.utc),
        approved_by=None,
        approved_at=None,
        executed_at=None,
        artifact_url=None,
        reject_reason=None,
    )


async def approve_request(
    db: AsyncSession,
    *,
    request_id: int,
    approver_id: int,
) -> None:
    """Mark a request approved. Enforces the two-person rule.

    The DB-level CHECK constraint makes this safe even if a future
    bug bypasses the explicit check — but we still error here for a
    friendly 403 instead of an IntegrityError surface.
    """
    row = (
        await db.execute(
            text(
                "SELECT status, requested_by FROM kvkk_export_requests "
                "WHERE id = :id"
            ),
            {"id": request_id},
        )
    ).first()
    if row is None:
        raise StateError("request_not_found")
    status, requested_by = row[0], int(row[1])
    if status != "requested":
        raise StateError(f"cannot_approve_in_status:{status}")
    if approver_id == requested_by:
        raise TwoPersonViolation(
            "Approver must differ from requester (KVKK two-person rule)"
        )
    await db.execute(
        text(
            """
            UPDATE kvkk_export_requests
               SET status      = 'approved',
                   approved_by = :by,
                   approved_at = now()
             WHERE id = :id
            """
        ),
        {"by": approver_id, "id": request_id},
    )
    await db.flush()
    logger.info(
        "KVKK export #%d approved by user %d (requested_by=%d)",
        request_id, approver_id, requested_by,
    )


async def reject_request(
    db: AsyncSession,
    *,
    request_id: int,
    approver_id: int,
    reason: str,
) -> None:
    """Reject the request. Same two-person rule applies to the
    rejecter so a malicious requester can't auto-cancel."""
    row = (
        await db.execute(
            text(
                "SELECT status, requested_by FROM kvkk_export_requests "
                "WHERE id = :id"
            ),
            {"id": request_id},
        )
    ).first()
    if row is None:
        raise StateError("request_not_found")
    status, requested_by = row[0], int(row[1])
    if status != "requested":
        raise StateError(f"cannot_reject_in_status:{status}")
    if approver_id == requested_by:
        raise TwoPersonViolation(
            "Rejecter must differ from requester (KVKK two-person rule)"
        )
    await db.execute(
        text(
            """
            UPDATE kvkk_export_requests
               SET status        = 'rejected',
                   approved_by   = :by,
                   approved_at   = now(),
                   reject_reason = :reason
             WHERE id = :id
            """
        ),
        {"by": approver_id, "id": request_id, "reason": reason[:1000]},
    )
    await db.flush()


async def mark_executing(db: AsyncSession, request_id: int) -> None:
    """Lock the request before the actual export job runs.

    Idempotency: a re-trigger after process restart sees status=
    'executing' and refuses to start a duplicate.
    """
    res = await db.execute(
        text(
            """
            UPDATE kvkk_export_requests
               SET status = 'executing'
             WHERE id = :id AND status = 'approved'
            """
        ),
        {"id": request_id},
    )
    if (res.rowcount or 0) == 0:
        raise StateError("must_be_approved_to_execute")
    await db.flush()


async def mark_done(
    db: AsyncSession, request_id: int, *, artifact_url: str
) -> None:
    """Final state. Artifact URL (S3 key / local path) recorded for
    later download + audit retention."""
    await db.execute(
        text(
            """
            UPDATE kvkk_export_requests
               SET status       = 'done',
                   executed_at  = now(),
                   artifact_url = :url
             WHERE id = :id
            """
        ),
        {"url": artifact_url[:500], "id": request_id},
    )
    await db.flush()


async def mark_failed(
    db: AsyncSession, request_id: int, *, reason: str
) -> None:
    await db.execute(
        text(
            """
            UPDATE kvkk_export_requests
               SET status        = 'failed',
                   reject_reason = :reason
             WHERE id = :id
            """
        ),
        {"reason": reason[:1000], "id": request_id},
    )
    await db.flush()
