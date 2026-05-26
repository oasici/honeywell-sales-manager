"""D-019 — Dead-Letter Queue for background jobs.

Pre-Round-19 the ``_tracked()`` wrapper in scheduler.py logged
failures but lost the failure context. A KVKK export that errored
out vanished into INFO logs. This module persists failures so:

  * Operators see them in the admin dashboard.
  * Failed jobs can be re-tried after fixing the root cause.
  * Audit trail of every background-job exception.

At 20-30 user scale this is a write-once table; alerting on
unresolved > 10 entries gives plenty of headroom.

To wire a new background task to the DLQ, the task either:
  (a) raises naturally (caught by ``_tracked()`` + ``_record_failure_to_dlq``)
  (b) catches its own exceptions + calls ``write_to_dlq`` directly
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class DlqEntry:
    id: int
    job_name: str
    payload: dict
    error: str
    failed_at: datetime
    retry_count: int
    resolved_at: Optional[datetime]
    note: Optional[str]


async def write_to_dlq(
    db: AsyncSession,
    *,
    job_name: str,
    error: str,
    payload: Optional[dict] = None,
) -> int:
    """Persist a job failure. Returns the new DLQ row id."""
    res = await db.execute(
        text(
            """
            INSERT INTO background_job_dlq (job_name, payload, error)
            VALUES (:n, CAST(:p AS jsonb), :e)
            RETURNING id
            """
        ),
        {
            "n": job_name,
            "p": json.dumps(payload or {}, default=str),
            "e": str(error)[:5000],
        },
    )
    new_id = res.scalar_one()
    await db.flush()
    logger.warning(
        "DLQ entry %d created: job=%s error=%s",
        new_id, job_name, str(error)[:200],
    )
    return int(new_id)


async def list_unresolved(
    db: AsyncSession, *, limit: int = 200
) -> list[DlqEntry]:
    rows = (
        await db.execute(
            text(
                """
                SELECT id, job_name, payload, error, failed_at,
                       retry_count, resolved_at, note
                  FROM background_job_dlq
                 WHERE resolved_at IS NULL
                 ORDER BY failed_at DESC
                 LIMIT :n
                """
            ),
            {"n": limit},
        )
    ).mappings().all()
    return [
        DlqEntry(
            id=r["id"],
            job_name=r["job_name"],
            payload=r["payload"] or {},
            error=r["error"],
            failed_at=r["failed_at"],
            retry_count=r["retry_count"],
            resolved_at=r["resolved_at"],
            note=r["note"],
        )
        for r in rows
    ]


async def mark_resolved(
    db: AsyncSession,
    *,
    dlq_id: int,
    user_id: int,
    note: Optional[str] = None,
) -> None:
    await db.execute(
        text(
            """
            UPDATE background_job_dlq
               SET resolved_at = now(),
                   resolved_by = :uid,
                   note        = :note
             WHERE id = :id AND resolved_at IS NULL
            """
        ),
        {"id": dlq_id, "uid": user_id, "note": (note or "")[:1000]},
    )
    await db.flush()


async def mark_retry_attempted(db: AsyncSession, *, dlq_id: int) -> None:
    await db.execute(
        text(
            "UPDATE background_job_dlq "
            "   SET retry_count = retry_count + 1 "
            " WHERE id = :id"
        ),
        {"id": dlq_id},
    )
    await db.flush()


async def count_unresolved(db: AsyncSession) -> int:
    row = (
        await db.execute(
            text(
                "SELECT COUNT(*) FROM background_job_dlq WHERE resolved_at IS NULL"
            )
        )
    ).first()
    return int(row[0]) if row else 0
