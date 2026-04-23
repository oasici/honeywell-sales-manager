"""Async audit log buffer — batches DB writes to reduce per-request overhead.

Collects audit entries in memory, flushes to DB every FLUSH_INTERVAL seconds
or when buffer reaches FLUSH_SIZE entries. Flush also happens on shutdown.

Worst-case data loss: up to FLUSH_SIZE entries or FLUSH_INTERVAL seconds of logs.
"""

import asyncio
import logging
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

FLUSH_INTERVAL = 5.0  # seconds
FLUSH_SIZE = 100  # max entries before forced flush

_buffer: list[dict] = []
_flush_task: asyncio.Task | None = None
_running = False


def enqueue_audit(
    user_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    ip_address: str,
) -> None:
    """Add an audit entry to the buffer (non-blocking, no DB call)."""
    _buffer.append({
        "user_id": user_id,
        "method": method,
        "path": path,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "ip_address": ip_address,
        "created_at": datetime.now(timezone.utc),
    })

    if len(_buffer) >= FLUSH_SIZE:
        asyncio.ensure_future(_flush_buffer())


async def _flush_buffer() -> None:
    """Flush buffered audit entries to DB."""
    if not _buffer:
        return

    entries = _buffer.copy()
    _buffer.clear()

    try:
        from app.core.database import async_session
        from app.models.audit_log import AuditLog

        async with async_session() as db:
            for entry in entries:
                changes = {
                    "method": entry.get("method"),
                    "path": entry.get("path"),
                    "status_code": entry.get("status_code"),
                    "duration_ms": entry.get("duration_ms"),
                    "created_at": entry.get("created_at").isoformat() if entry.get("created_at") else None,
                }
                db.add(AuditLog(
                    user_id=int(entry["user_id"]) if entry["user_id"] != "anonymous" else None,
                    action=entry["method"],
                    entity_type="api_request",
                    entity_id=0,
                    ip_address=entry["ip_address"],
                    changes=json.dumps(changes, ensure_ascii=False, default=str),
                ))
            await db.commit()
            logger.debug("Flushed %d audit entries to DB", len(entries))
    except Exception as e:
        logger.error("Audit buffer flush failed: %s (lost %d entries)", e, len(entries))


async def _periodic_flush() -> None:
    """Background task that flushes buffer periodically."""
    global _running
    while _running:
        await asyncio.sleep(FLUSH_INTERVAL)
        await _flush_buffer()


def start_audit_buffer() -> None:
    """Start the periodic flush background task."""
    global _flush_task, _running
    _running = True
    try:
        loop = asyncio.get_running_loop()
        _flush_task = loop.create_task(_periodic_flush())
    except RuntimeError:
        pass


async def stop_audit_buffer() -> None:
    """Flush remaining entries and stop the background task."""
    global _flush_task, _running
    _running = False
    if _flush_task:
        _flush_task.cancel()
        _flush_task = None
    await _flush_buffer()
