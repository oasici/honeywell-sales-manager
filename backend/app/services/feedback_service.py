"""Track user corrections to AI parse results for continuous improvement."""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


async def record_parse_correction(
    db: AsyncSession,
    email_id: int,
    user_id: int,
    field: str,
    original_value: str,
    corrected_value: str,
) -> None:
    """Record when a user corrects an AI parse result."""
    log = AuditLog(
        user_id=user_id,
        action="ai_correction",
        entity_type="email_parse",
        entity_id=email_id,
        changes=json.dumps({
            "field": field,
            "original": original_value,
            "corrected": corrected_value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }),
    )
    db.add(log)
    await db.flush()
    logger.info("AI correction recorded: email=%d field=%s", email_id, field)


async def get_correction_stats(db: AsyncSession, days: int = 30) -> dict:
    """Get stats on AI parse corrections for monitoring accuracy."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    result = await db.execute(
        select(func.count(AuditLog.id).label("total_corrections"))
        .where(AuditLog.action == "ai_correction")
        .where(AuditLog.created_at >= cutoff),
    )
    row = result.first()

    # Get most corrected fields
    field_result = await db.execute(
        select(AuditLog.changes)
        .where(AuditLog.action == "ai_correction")
        .where(AuditLog.created_at >= cutoff)
        .limit(100),
    )

    field_counts: dict[str, int] = {}
    for (changes_json,) in field_result:
        if not changes_json:
            continue
        try:
            data = json.loads(changes_json)
            field = data.get("field", "unknown")
            field_counts[field] = field_counts.get(field, 0) + 1
        except json.JSONDecodeError:
            pass

    top_fields = dict(sorted(field_counts.items(), key=lambda x: -x[1])[:5])

    return {
        "total_corrections": row.total_corrections if row else 0,
        "period_days": days,
        "top_corrected_fields": top_fields,
    }
