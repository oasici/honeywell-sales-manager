"""Transcript katılımcı satırlarından kural tabanlı stakeholder önerisi (Sprint 4).

FEATURE_BUYER_MAP açıkken engagement.create_transcript bu servisi çağırır.
LLM yok — virgül/noktalı virgül/satır ve \"Ad <email>\" desenleri ayrıştırılır.
"""

from __future__ import annotations

import re
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.engagement import Transcript
from app.models.sequence_v2 import Stakeholder


_EMAIL_IN_ANGLE = re.compile(r"^\s*(.+?)\s*<([^>]+)>\s*$", re.I)
_EMAIL_ONLY = re.compile(r"^[\w.+-]+@[\w.-]+\.\w{2,}$", re.I)


def _split_participant_blob(raw: str) -> list[str]:
    parts: list[str] = []
    for chunk in re.split(r"[\n;,]+", raw):
        s = chunk.strip()
        if len(s) >= 2:
            parts.append(s)
    return parts


def parse_participant_tokens(raw: str | None) -> list[tuple[str, str | None]]:
    """İsim + isteğe bağlı e-posta çiftleri döndür."""
    if not raw or not raw.strip():
        return []
    out: list[tuple[str, str | None]] = []
    for piece in _split_participant_blob(raw):
        m = _EMAIL_IN_ANGLE.match(piece)
        if m:
            name = m.group(1).strip().strip('"').strip("'")
            email = m.group(2).strip()
            if name:
                out.append((name[:200], email if _EMAIL_ONLY.match(email) else None))
            continue
        if _EMAIL_ONLY.match(piece):
            local = piece.split("@", 1)[0].replace(".", " ").replace("_", " ")
            guess = " ".join(w.capitalize() for w in local.split() if w) or piece.split("@", 1)[0]
            out.append((guess[:200], piece))
            continue
        if len(piece) >= 2:
            out.append((piece[:200], None))
    return out


async def _exists_duplicate(
    db: AsyncSession,
    *,
    opportunity_id: int | None,
    customer_id: int | None,
    name: str,
    email: str | None,
) -> bool:
    match_parts = [func.lower(Stakeholder.name) == name.strip().lower()]
    if email:
        match_parts.append(Stakeholder.email == email)
    q = select(Stakeholder.id).where(or_(*match_parts))
    if opportunity_id is not None:
        q = q.where(Stakeholder.opportunity_id == opportunity_id)
    elif customer_id is not None:
        q = q.where(Stakeholder.customer_id == customer_id)
    else:
        return False
    row = (await db.execute(q.limit(1))).scalar_one_or_none()
    return row is not None


async def enrich_from_transcript(
    db: AsyncSession,
    transcript: Transcript,
    created_by_user_id: int,
) -> list[int]:
    """Transcript.participants alanından otomatik stakeholder satırları ekler."""
    if not transcript.participants or not transcript.participants.strip():
        return []
    if transcript.opportunity_id is None and transcript.customer_id is None:
        return []

    # Round-16 N15-DB-3 cohort-9 — Stakeholder.tenant_id is now NOT
    # NULL. Derive from the parent opportunity (preferred) or
    # customer; both carry the canonical tenant for this record.
    derived_tenant_id: int | None = None
    if transcript.opportunity_id is not None:
        from app.models.opportunity import Opportunity

        row = await db.execute(
            select(Opportunity.tenant_id).where(
                Opportunity.id == transcript.opportunity_id
            )
        )
        derived_tenant_id = row.scalar_one_or_none()
    if derived_tenant_id is None and transcript.customer_id is not None:
        from app.models.customer import Customer

        row = await db.execute(
            select(Customer.tenant_id).where(Customer.id == transcript.customer_id)
        )
        derived_tenant_id = row.scalar_one_or_none()

    created: list[int] = []
    for name, email in parse_participant_tokens(transcript.participants):
        if len(name.strip()) < 2:
            continue
        dup = await _exists_duplicate(
            db,
            opportunity_id=transcript.opportunity_id,
            customer_id=transcript.customer_id,
            name=name,
            email=email,
        )
        if dup:
            continue
        s = Stakeholder(
            tenant_id=derived_tenant_id,
            opportunity_id=transcript.opportunity_id,
            customer_id=transcript.customer_id,
            name=name,
            email=email,
            title=None,
            phone=None,
            seniority=None,
            department_group=None,
            buyer_role=None,
            notes="Transcript katilimcilarindan otomatik eklendi",
            is_auto_detected=True,
            created_by=created_by_user_id,
        )
        db.add(s)
        await db.flush()
        created.append(s.id)
    return created
