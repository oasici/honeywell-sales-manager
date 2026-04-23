"""Sprint 5 — conversation insights, signal trends, unified conversation search."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_request import EmailRequest
from app.models.engagement import Transcript
from app.models.enums import UserRole
from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal
from app.models.user import User

# Transcript / note keyword buckets (MVP — complements structured OpportunitySignal).
KEYWORD_GROUPS: dict[str, list[str]] = {
    "pricing": ["fiyat", "pricing", "bütçe", "budget", "ücret", "maliyet", "discount", "indirim"],
    "objection": ["objection", "itiraz", "endişe", "concern", "risk", "tereddüt", "doubt"],
    "competitor": ["rakip", "competitor", "alternatif", "alternative", "pazar"],
}


def _ilike_pattern(term: str) -> str:
    safe = term.replace("%", "\\%").replace("_", "\\_")
    return f"%{safe}%"


def _snippet(text: str | None, needle: str, max_len: int = 200) -> str:
    if not text:
        return ""
    t = re.sub(r"\s+", " ", text).strip()
    if not needle:
        return t[:max_len]
    low = t.lower()
    idx = low.find(needle.lower())
    if idx < 0:
        return t[:max_len]
    pad = max_len // 2
    start = max(0, idx - pad)
    return ("…" if start > 0 else "") + t[start : start + max_len] + ("…" if start + max_len < len(t) else "")


async def signal_trends(db: AsyncSession, *, window_days: int) -> dict:
    """Daily signal counts for charting (UTC date bucket)."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    day_col = func.date(OpportunitySignal.created_at)

    rows = (
        await db.execute(
            select(day_col, OpportunitySignal.signal_type, func.count(OpportunitySignal.id))
            .where(OpportunitySignal.created_at >= cutoff)
            .group_by(day_col, OpportunitySignal.signal_type)
            .order_by(day_col)
        )
    ).all()

    by_date: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for d, st, cnt in rows:
        ds = d.isoformat() if hasattr(d, "isoformat") else str(d)
        by_date[ds][str(st)] += int(cnt or 0)
        by_date[ds]["total"] += int(cnt or 0)

    series = []
    for ds in sorted(by_date.keys()):
        row = {"date": ds, "total": by_date[ds].get("total", 0)}
        for k in ("pricing_concern", "competitor", "objection", "no_touch", "discount_risk"):
            row[k] = by_date[ds].get(k, 0)
        series.append(row)

    return {"window_days": window_days, "series": series}


async def conversation_insights_keywords(db: AsyncSession, *, window_days: int) -> dict:
    """Keyword-style hits on transcripts (Sprint 5 ConversationInsights MVP)."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=window_days)
    hits: dict[str, int] = {}
    for key, terms in KEYWORD_GROUPS.items():
        term_conds = [
            or_(Transcript.title.ilike(_ilike_pattern(t)), Transcript.content.ilike(_ilike_pattern(t)))
            for t in terms
        ]
        n = (
            await db.execute(
                select(func.count(Transcript.id)).where(
                    and_(Transcript.created_at >= cutoff, Transcript.opportunity_id.isnot(None), or_(*term_conds)),
                )
            )
        ).scalar() or 0
        hits[key] = int(n)
    return {"window_days": window_days, "transcript_keyword_hits": hits}


def _opp_scope_clauses(
    user: User,
    *,
    stage: str | None,
    owner_id: int | None,
    signal_type: str | None,
) -> list:
    clauses: list = []
    if user.role != UserRole.SALES_MANAGER.value:
        clauses.append(Opportunity.owner_id == user.id)
    elif owner_id is not None:
        clauses.append(Opportunity.owner_id == owner_id)
    if stage:
        clauses.append(Opportunity.stage == stage)
    if signal_type:
        sig_opp_ids = (
            select(OpportunitySignal.opportunity_id)
            .where(
                OpportunitySignal.signal_type == signal_type,
                OpportunitySignal.is_resolved.is_(False),
            )
            .distinct()
        )
        clauses.append(Opportunity.id.in_(sig_opp_ids))
    return clauses


async def conversation_search(
    db: AsyncSession,
    user: User,
    *,
    q: str,
    stage: str | None,
    signal_type: str | None,
    owner_id: int | None,
    page: int,
    page_size: int,
) -> dict:
    """Unified search across transcripts, inbound emails, and timeline notes."""
    if len(q.strip()) < 2:
        return {"query": q, "page": page, "page_size": page_size, "total": 0, "items": []}

    pattern = _ilike_pattern(q.strip())
    scope = _opp_scope_clauses(user, stage=stage, owner_id=owner_id, signal_type=signal_type)

    items: list[dict] = []

    # Transcripts
    t_clauses = [
        Transcript.opportunity_id.isnot(None),
        or_(Transcript.title.ilike(pattern), Transcript.content.ilike(pattern)),
        *scope,
    ]
    tr_rows = (
        await db.execute(
            select(Transcript, Opportunity)
            .join(Opportunity, Transcript.opportunity_id == Opportunity.id)
            .where(and_(*t_clauses))
            .order_by(Transcript.created_at.desc())
            .limit(80)
        )
    ).all()
    for tr, opp in tr_rows:
        items.append(
            {
                "type": "transcript",
                "id": tr.id,
                "title": tr.title,
                "snippet": _snippet(tr.content, q.strip()),
                "opportunity_id": opp.id,
                "stage": opp.stage,
                "owner_id": opp.owner_id,
                "occurred_at": tr.created_at.isoformat() if tr.created_at else None,
            }
        )

    # Inbound emails (linked to opportunity)
    e_clauses = [
        EmailRequest.opportunity_id.isnot(None),
        or_(
            EmailRequest.subject.ilike(pattern),
            EmailRequest.body_text.ilike(pattern),
            EmailRequest.body_html.ilike(pattern),
        ),
        *scope,
    ]
    em_rows = (
        await db.execute(
            select(EmailRequest, Opportunity)
            .join(Opportunity, EmailRequest.opportunity_id == Opportunity.id)
            .where(and_(*e_clauses))
            .order_by(EmailRequest.created_at.desc())
            .limit(80)
        )
    ).all()
    for em, opp in em_rows:
        blob = em.subject or em.body_text or em.body_html or ""
        items.append(
            {
                "type": "email",
                "id": em.id,
                "title": em.subject or "(no subject)",
                "snippet": _snippet(blob, q.strip()),
                "opportunity_id": opp.id,
                "stage": opp.stage,
                "owner_id": opp.owner_id,
                "occurred_at": em.created_at.isoformat() if em.created_at else None,
            }
        )

    # Notes on opportunity timeline
    n_clauses = [
        OpportunityEvent.event_type == "note",
        OpportunityEvent.description.isnot(None),
        OpportunityEvent.description.ilike(pattern),
        *scope,
    ]
    note_rows = (
        await db.execute(
            select(OpportunityEvent, Opportunity)
            .join(Opportunity, OpportunityEvent.opportunity_id == Opportunity.id)
            .where(and_(*n_clauses))
            .order_by(OpportunityEvent.occurred_at.desc())
            .limit(80)
        )
    ).all()
    for ev, opp in note_rows:
        desc = ev.description or ""
        items.append(
            {
                "type": "note",
                "id": ev.id,
                "title": "Note",
                "snippet": _snippet(desc, q.strip()),
                "opportunity_id": opp.id,
                "stage": opp.stage,
                "owner_id": opp.owner_id,
                "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
            }
        )

    def sort_key(row: dict) -> datetime:
        raw = row.get("occurred_at")
        if not raw:
            return datetime.min.replace(tzinfo=timezone.utc)
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return datetime.min.replace(tzinfo=timezone.utc)

    items.sort(key=sort_key, reverse=True)
    total = len(items)
    start = (page - 1) * page_size
    page_items = items[start : start + page_size]

    return {
        "query": q.strip(),
        "page": page,
        "page_size": page_size,
        "total": total,
        "items": page_items,
    }
