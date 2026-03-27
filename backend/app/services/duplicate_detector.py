"""Duplicate email detection using sentence embeddings.

Compares incoming email body against recent emails (last 7 days) using
cosine similarity. Flags potential duplicates above threshold.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_request import EmailRequest

logger = logging.getLogger(__name__)

DUPLICATE_THRESHOLD = 0.85
LOOKBACK_DAYS = 7


async def check_duplicate(
    db: AsyncSession,
    body_text: str,
    from_address: str | None = None,
) -> dict[str, Any] | None:
    """Check if an incoming email is a duplicate of a recent one.

    Returns duplicate info dict or None if no duplicate found.
    """
    if not body_text or len(body_text.strip()) < 20:
        return None

    try:
        from app.services.semantic_matcher import _get_model
        model = _get_model()
        if model is None:
            return None
    except Exception:
        return None

    import numpy as np

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

    # Fetch recent emails
    filters = [EmailRequest.created_at >= cutoff]
    if from_address:
        filters.append(EmailRequest.from_address == from_address)

    result = await db.execute(
        select(EmailRequest)
        .where(and_(*filters))
        .order_by(EmailRequest.created_at.desc())
        .limit(100)
    )
    recent_emails = result.scalars().all()

    if not recent_emails:
        return None

    # Get texts from recent emails
    recent_texts = []
    recent_ids = []
    for email in recent_emails:
        text = email.body_text or ""
        if len(text.strip()) >= 20:
            recent_texts.append(text[:500])  # Truncate for performance
            recent_ids.append(email.id)

    if not recent_texts:
        return None

    # Encode all texts
    query_vec = model.encode([body_text[:500]], normalize_embeddings=True)
    recent_vecs = model.encode(recent_texts, normalize_embeddings=True)

    # Cosine similarity
    scores = np.dot(recent_vecs, query_vec.T).flatten()

    max_idx = int(np.argmax(scores))
    max_score = float(scores[max_idx])

    if max_score >= DUPLICATE_THRESHOLD:
        dup_email = recent_emails[max_idx] if max_idx < len(recent_emails) else None
        return {
            "is_duplicate": True,
            "similarity_score": round(max_score * 100, 1),
            "duplicate_email_id": recent_ids[max_idx],
            "duplicate_subject": dup_email.subject if dup_email else None,
            "duplicate_date": dup_email.created_at.isoformat() if dup_email and dup_email.created_at else None,
        }

    return None
