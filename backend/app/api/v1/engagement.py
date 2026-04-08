"""v2 Engagement endpoints — transcripts, keyword packs, sequences, segments, NL search, coaching.

All free-tier compatible (no external paid APIs required):
- Transcripts: plain text upload + PostgreSQL full-text search
- Keyword packs: configurable JSON arrays in DB
- Sequences: step-based JSON definitions + scheduler enrollment
- Segments: rule-based customer grouping with JSON rules
"""

import json
import logging
import math
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_role
from app.core.exceptions import BadRequestException, NotFoundException
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.engagement import Transcript, KeywordPack, Sequence, SequenceEnrollment, Segment
from app.models.enums import UserRole
from app.models.opportunity import Opportunity, OpportunitySignal
from app.models.quote import Quote
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Engagement (v2)"])


# ══════════════════════════════════════════
# TRANSCRIPTS — upload, search, keyword scan
# ══════════════════════════════════════════

class TranscriptCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=10)
    opportunity_id: int | None = None
    customer_id: int | None = None
    source: str = "upload"
    duration_minutes: int | None = None
    participants: str | None = None


@router.post("/transcripts/", status_code=201)
async def create_transcript(
    body: TranscriptCreate,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Upload/paste a call/meeting transcript."""
    # Auto-scan for keywords
    keywords_found = _scan_keywords_in_text(body.content, await _get_active_keywords(db))

    t = Transcript(
        title=body.title,
        content=body.content,
        opportunity_id=body.opportunity_id,
        customer_id=body.customer_id,
        source=body.source,
        duration_minutes=body.duration_minutes,
        participants=body.participants,
        keywords_found=json.dumps(keywords_found, ensure_ascii=False) if keywords_found else None,
        created_by=current_user.id,
    )
    db.add(t)
    await db.flush()
    await db.refresh(t)

    # Auto-create signals if linked to opportunity
    if body.opportunity_id and keywords_found:
        for kw_info in keywords_found:
            db.add(OpportunitySignal(
                opportunity_id=body.opportunity_id,
                signal_type=kw_info["category"],
                severity="med",
                evidence=f"Transkriptte tespit: {kw_info['keyword']}",
                source_type="transcript",
                source_id=t.id,
            ))
        await db.flush()

    return {
        "id": t.id, "title": t.title, "keywords_found": keywords_found,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/transcripts/")
async def list_transcripts(
    opportunity_id: int | None = None,
    customer_id: int | None = None,
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List transcripts with optional filters."""
    query = select(Transcript)
    conditions = []
    if opportunity_id:
        conditions.append(Transcript.opportunity_id == opportunity_id)
    if customer_id:
        conditions.append(Transcript.customer_id == customer_id)
    if conditions:
        query = query.where(and_(*conditions))

    total = (await db.execute(select(func.count(Transcript.id)).where(and_(*conditions) if conditions else True))).scalar() or 0
    offset = (page - 1) * page_size
    result = await db.execute(query.order_by(Transcript.created_at.desc()).offset(offset).limit(page_size))
    items = result.scalars().all()

    return {
        "items": [
            {
                "id": t.id, "title": t.title, "source": t.source,
                "opportunity_id": t.opportunity_id, "customer_id": t.customer_id,
                "duration_minutes": t.duration_minutes,
                "keywords_found": json.loads(t.keywords_found) if t.keywords_found else [],
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in items
        ],
        "total": total, "page": page, "page_size": page_size,
    }


@router.get("/transcripts/search")
async def search_transcripts(
    q: str = Query(..., min_length=2, description="Search query"),
    opportunity_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Semantic search across transcripts.

    Uses pgvector + sentence-transformers when available (semantic similarity).
    Falls back to PostgreSQL ILIKE + pg_trgm (keyword + fuzzy match).
    All free, no external paid APIs.
    """
    from app.services.vector_search import semantic_search

    filters = {}
    if opportunity_id:
        filters["opportunity_id"] = opportunity_id

    semantic_results = await semantic_search(
        db, query=q, table="transcripts", content_column="content",
        limit=page_size, filters=filters if filters else None,
    )

    if semantic_results:
        return {
            "query": q,
            "total": len(semantic_results),
            "search_method": "semantic" if any(r["score"] != 0.5 for r in semantic_results) else "ilike",
            "items": semantic_results,
        }

    # Fallback: basic ILIKE if semantic_search returned nothing
    safe_q = q.replace("%", "\\%").replace("_", "\\_")
    search_term = f"%{safe_q}%"
    query_stmt = select(Transcript).where(
        or_(Transcript.content.ilike(search_term), Transcript.title.ilike(search_term))
    )
    if opportunity_id:
        query_stmt = query_stmt.where(Transcript.opportunity_id == opportunity_id)

    total = (await db.execute(
        select(func.count(Transcript.id)).where(
            or_(Transcript.content.ilike(search_term), Transcript.title.ilike(search_term))
        )
    )).scalar() or 0

    result = await db.execute(query_stmt.order_by(Transcript.created_at.desc()).offset((page-1)*page_size).limit(page_size))
    items = result.scalars().all()

    return {
        "query": q,
        "total": total,
        "search_method": "ilike_fallback",
        "items": [
            {
                "id": t.id, "title": t.title,
                "snippet": _extract_snippet(t.content, q, 200),
                "opportunity_id": t.opportunity_id,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in items
        ],
    }


# ══════════════════════════════════════════
# KEYWORD PACKS — configurable signal keywords
# ══════════════════════════════════════════

class KeywordPackCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    category: str  # pricing | competitor | objection | positive | technical | custom
    keywords: list[str]


@router.get("/keyword-packs/")
async def list_keyword_packs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all keyword packs."""
    packs = (await db.execute(select(KeywordPack).order_by(KeywordPack.name))).scalars().all()
    return {
        "packs": [
            {"id": p.id, "name": p.name, "category": p.category,
             "keywords": json.loads(p.keywords_json) if p.keywords_json else [],
             "is_active": p.is_active}
            for p in packs
        ],
    }


@router.post("/keyword-packs/", status_code=201)
async def create_keyword_pack(
    body: KeywordPackCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a keyword pack for signal detection."""
    pack = KeywordPack(
        name=body.name, category=body.category,
        keywords_json=json.dumps(body.keywords, ensure_ascii=False),
    )
    db.add(pack)
    await db.flush()
    await db.refresh(pack)
    return {"id": pack.id, "name": pack.name, "category": pack.category}


# ══════════════════════════════════════════
# SEQUENCES — automated follow-up steps
# ══════════════════════════════════════════

class SequenceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    steps: list[dict]  # [{"step":1,"action":"email|task","delay_days":0,"template":"..."}]


@router.get("/sequences/")
async def list_sequences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sequences."""
    seqs = (await db.execute(select(Sequence).where(Sequence.is_active.is_(True)))).scalars().all()
    return {
        "sequences": [
            {"id": s.id, "name": s.name, "description": s.description,
             "steps": json.loads(s.steps_json) if s.steps_json else [],
             "created_at": s.created_at.isoformat() if s.created_at else None}
            for s in seqs
        ],
    }


@router.post("/sequences/", status_code=201)
async def create_sequence(
    body: SequenceCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create an automated follow-up sequence."""
    seq = Sequence(
        name=body.name, description=body.description,
        steps_json=json.dumps(body.steps, ensure_ascii=False),
        created_by=current_user.id,
    )
    db.add(seq)
    await db.flush()
    await db.refresh(seq)
    return {"id": seq.id, "name": seq.name}


class EnrollRequest(BaseModel):
    sequence_id: int
    opportunity_id: int | None = None
    customer_id: int | None = None


@router.post("/sequences/enroll", status_code=201)
async def enroll_in_sequence(
    body: EnrollRequest,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Enroll an opportunity/customer in a sequence."""
    seq = (await db.execute(select(Sequence).where(Sequence.id == body.sequence_id))).scalar_one_or_none()
    if not seq:
        raise NotFoundException("Sira bulunamadi")

    enrollment = SequenceEnrollment(
        sequence_id=body.sequence_id,
        opportunity_id=body.opportunity_id,
        customer_id=body.customer_id,
        enrolled_by=current_user.id,
        next_action_at=datetime.now(timezone.utc),
    )
    db.add(enrollment)
    await db.flush()
    await db.refresh(enrollment)
    return {"id": enrollment.id, "status": enrollment.status, "current_step": enrollment.current_step}


# ══════════════════════════════════════════
# SEGMENTS — rule-based customer grouping
# ══════════════════════════════════════════

class SegmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    rules: list[dict]  # [{"field":"company","op":"contains","value":"sanayi"}]


@router.get("/segments/")
async def list_segments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all customer segments."""
    segs = (await db.execute(select(Segment).order_by(Segment.name))).scalars().all()
    return {
        "segments": [
            {"id": s.id, "name": s.name, "description": s.description,
             "rules": json.loads(s.rules_json) if s.rules_json else [],
             "customer_count": s.customer_count,
             "created_at": s.created_at.isoformat() if s.created_at else None}
            for s in segs
        ],
    }


@router.post("/segments/", status_code=201)
async def create_segment(
    body: SegmentCreate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Create a customer segment with rules."""
    # Count matching customers
    count = await _count_segment_customers(db, body.rules)

    seg = Segment(
        name=body.name, description=body.description,
        rules_json=json.dumps(body.rules, ensure_ascii=False),
        customer_count=count,
        created_by=current_user.id,
    )
    db.add(seg)
    await db.flush()
    await db.refresh(seg)
    return {"id": seg.id, "name": seg.name, "customer_count": count}


@router.get("/segments/{segment_id}/customers")
async def get_segment_customers(
    segment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List customers matching a segment's rules."""
    seg = (await db.execute(select(Segment).where(Segment.id == segment_id))).scalar_one_or_none()
    if not seg:
        raise NotFoundException("Segment bulunamadi")

    rules = json.loads(seg.rules_json) if seg.rules_json else []
    customers = await _filter_customers_by_rules(db, rules)

    return {
        "segment_id": segment_id,
        "segment_name": seg.name,
        "customers": [
            {"id": c.id, "name": c.name, "company": c.company, "email": c.email}
            for c in customers
        ],
    }


# ══════════════════════════════════════════
# COACHING SCORECARDS
# ══════════════════════════════════════════

@router.get("/coaching/scorecards")
async def get_coaching_scorecards(
    window: int = Query(30, ge=7, le=365),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Coaching scorecards — rep performance + signal handling + response patterns."""
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)

    reps = (await db.execute(
        select(User).where(User.role.in_(["sales_rep", "sales_manager"]), User.is_active.is_(True))
    )).scalars().all()

    scorecards = []
    for rep in reps:
        # Quote metrics
        total_quotes = (await db.execute(
            select(func.count(Quote.id)).where(Quote.created_by == rep.id, Quote.created_at >= cutoff)
        )).scalar() or 0
        sent_quotes = (await db.execute(
            select(func.count(Quote.id)).where(Quote.created_by == rep.id, Quote.status == "sent", Quote.created_at >= cutoff)
        )).scalar() or 0

        # Email response (emails assigned + processed)
        emails_assigned = (await db.execute(
            select(func.count(EmailRequest.id)).where(EmailRequest.assigned_to == rep.id, EmailRequest.created_at >= cutoff)
        )).scalar() or 0
        emails_processed = (await db.execute(
            select(func.count(EmailRequest.id)).where(
                EmailRequest.assigned_to == rep.id, EmailRequest.status != "new", EmailRequest.created_at >= cutoff
            )
        )).scalar() or 0

        # Opportunity signals resolved
        signals_total = (await db.execute(
            select(func.count(OpportunitySignal.id))
            .join(Opportunity, OpportunitySignal.opportunity_id == Opportunity.id)
            .where(Opportunity.owner_id == rep.id, OpportunitySignal.created_at >= cutoff)
        )).scalar() or 0

        process_rate = round(emails_processed / emails_assigned * 100, 1) if emails_assigned > 0 else 0

        scorecards.append({
            "user_id": rep.id,
            "full_name": rep.full_name,
            "total_quotes": total_quotes,
            "sent_quotes": sent_quotes,
            "emails_assigned": emails_assigned,
            "emails_processed": emails_processed,
            "process_rate": process_rate,
            "signals_detected": signals_total,
            "coaching_notes": _generate_coaching_notes(total_quotes, sent_quotes, process_rate),
        })

    scorecards.sort(key=lambda x: x["process_rate"], reverse=True)
    return {"window_days": window, "scorecards": scorecards}


# ══════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════

async def _get_active_keywords(db: AsyncSession) -> list[dict]:
    """Get all active keyword packs as flat list."""
    packs = (await db.execute(select(KeywordPack).where(KeywordPack.is_active.is_(True)))).scalars().all()
    result = []
    for p in packs:
        keywords = json.loads(p.keywords_json) if p.keywords_json else []
        for kw in keywords:
            result.append({"keyword": kw.lower(), "category": p.category, "pack": p.name})
    return result


def _scan_keywords_in_text(text: str, keywords: list[dict]) -> list[dict]:
    """Scan text for keywords from active packs."""
    text_lower = text.lower()
    found = []
    seen = set()
    for kw_info in keywords:
        if kw_info["keyword"] in text_lower and kw_info["keyword"] not in seen:
            found.append(kw_info)
            seen.add(kw_info["keyword"])
    return found


def _extract_snippet(text: str, query: str, max_len: int = 200) -> str:
    """Extract a text snippet around the first occurrence of query."""
    idx = text.lower().find(query.lower())
    if idx == -1:
        return text[:max_len] + ("..." if len(text) > max_len else "")
    start = max(0, idx - 50)
    end = min(len(text), idx + len(query) + 150)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


async def _count_segment_customers(db: AsyncSession, rules: list[dict]) -> int:
    """Count customers matching segment rules."""
    customers = await _filter_customers_by_rules(db, rules)
    return len(customers)


async def _filter_customers_by_rules(db: AsyncSession, rules: list[dict]) -> list:
    """Filter customers by segment rules — extended rule engine.

    Supported operators:
    - contains: ILIKE substring match
    - equals: exact match
    - not_empty: field is not null and not empty string
    - gte: greater than or equal (numeric/date)
    - lte: less than or equal (numeric/date)
    - in: value in comma-separated list
    - not_equals: not equal
    - starts_with: ILIKE prefix match

    Aggregate operators (cross-table):
    - quote_count_gte: customers with >= N quotes
    - quote_value_gte: customers with total quote value >= N
    - last_quote_within_days: customers with a quote in last N days
    """
    from datetime import timedelta

    query = select(Customer)
    aggregate_filters = []

    for rule in rules:
        field = rule.get("field", "")
        op = rule.get("op", "")
        value = rule.get("value", "")

        # Aggregate rules (cross-table)
        if field == "quote_count" and op == "gte":
            aggregate_filters.append(("quote_count_gte", float(value)))
            continue
        if field == "quote_value" and op == "gte":
            aggregate_filters.append(("quote_value_gte", float(value)))
            continue
        if field == "last_quote_within_days":
            aggregate_filters.append(("last_quote_days", int(value)))
            continue

        # Standard field rules
        if not hasattr(Customer, field):
            continue

        col = getattr(Customer, field)
        if op == "contains":
            safe_val = str(value).replace("%", "\\%").replace("_", "\\_")
            query = query.where(col.ilike(f"%{safe_val}%"))
        elif op == "equals":
            query = query.where(col == value)
        elif op == "not_equals":
            query = query.where(col != value)
        elif op == "not_empty":
            query = query.where(col.isnot(None), col != "")
        elif op == "gte":
            query = query.where(col >= float(value))
        elif op == "lte":
            query = query.where(col <= float(value))
        elif op == "in":
            vals = [v.strip() for v in str(value).split(",")]
            query = query.where(col.in_(vals))
        elif op == "starts_with":
            safe_val = str(value).replace("%", "\\%").replace("_", "\\_")
            query = query.where(col.ilike(f"{safe_val}%"))

    result = await db.execute(query.limit(1000))
    customers = list(result.scalars().all())

    # Apply aggregate filters (post-query)
    if aggregate_filters:
        filtered = []
        for c in customers:
            include = True
            for agg_type, agg_val in aggregate_filters:
                if agg_type == "quote_count_gte":
                    count = (await db.execute(
                        select(func.count(Quote.id)).where(Quote.customer_id == c.id)
                    )).scalar() or 0
                    if count < agg_val:
                        include = False
                elif agg_type == "quote_value_gte":
                    total = (await db.execute(
                        select(func.coalesce(func.sum(Quote.grand_total), 0.0)).where(Quote.customer_id == c.id)
                    )).scalar() or 0
                    if float(total) < agg_val:
                        include = False
                elif agg_type == "last_quote_days":
                    cutoff = datetime.now(timezone.utc) - timedelta(days=int(agg_val))
                    latest = (await db.execute(
                        select(func.max(Quote.created_at)).where(Quote.customer_id == c.id)
                    )).scalar()
                    if not latest:
                        include = False
                    else:
                        if latest.tzinfo is None:
                            from datetime import timezone as tz
                            latest = latest.replace(tzinfo=tz.utc)
                        if latest < cutoff:
                            include = False
            if include:
                filtered.append(c)
        return filtered[:500]

    return customers[:500]


def _generate_coaching_notes(total_quotes: int, sent_quotes: int, process_rate: float) -> list[str]:
    """Generate coaching suggestions based on metrics."""
    notes = []
    if total_quotes == 0:
        notes.append("Bu donemde teklif olusturulmamis — email atamasini kontrol edin.")
    elif sent_quotes == 0 and total_quotes > 0:
        notes.append("Teklifler olusturulmus ama hicbiri gonderilmemis — onay surecini kontrol edin.")
    if process_rate < 50:
        notes.append("Email isleme orani dusuk — is yukunu dengelemeyi degerlendirin.")
    if process_rate >= 90:
        notes.append("Mukemmel email isleme performansi — ornek olarak paylasabilirsiniz.")
    return notes
