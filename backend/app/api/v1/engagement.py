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

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
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
from app.services.tenant_context import assert_same_tenant, scoped_for_user
from app.schemas.common import PaginatedResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Engagement"])

# Backward-compatible mount is defined at the bottom of this module — after
# every @router.<method> decorator has registered — so include_router sees
# the full route list. Importers must pull both ``router`` (canonical paths)
# and ``legacy_router`` (``/engagement/*`` paths).
#
# DEPRECATED: scheduled for removal 2026-09. Frontend should migrate to the
# canonical ``router`` paths; the dependency below logs and tags every hit
# so we can quantify remaining traffic before deletion.
async def _legacy_engagement_warning(request: Request) -> None:
    logger.warning(
        "Deprecated /engagement/* endpoint hit: %s %s — migrate caller before 2026-09",
        request.method,
        request.url.path,
    )

legacy_router = APIRouter(
    prefix="/engagement",
    tags=["Engagement (deprecated)"],
    deprecated=True,
    dependencies=[Depends(_legacy_engagement_warning)],
)


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
        from app.services.dedupe_service import upsert_opportunity_signal
        for kw_info in keywords_found:
            await upsert_opportunity_signal(
                db,
                opportunity_id=body.opportunity_id,
                signal_type=kw_info["category"],
                severity="med",
                evidence=f"Transkriptte tespit: {kw_info['keyword']}",
                source_type="transcript",
                source_id=t.id,
            )
        await db.flush()

    if settings.FEATURE_BUYER_MAP and body.participants and (
        body.opportunity_id is not None or body.customer_id is not None
    ):
        from app.services.stakeholder_enrichment_service import enrich_from_transcript

        created_ids = await enrich_from_transcript(db, t, current_user.id)
        if created_ids:
            await db.flush()

    # V11 RAG hook: index the transcript into the interactions
    # collection so subsequent /rag/answer queries can retrieve it.
    # Best-effort — non-blocking, no-op when FEATURE_RAG=false.
    if settings.FEATURE_RAG:
        try:
            from app.services.rag_backfill_service import index_transcript_now

            await index_transcript_now(int(t.id))
        except Exception:
            pass

    return {
        "id": t.id, "title": t.title, "keywords_found": keywords_found,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


@router.get("/transcripts/", response_model=PaginatedResponse[dict])
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

    import math as _math

    return {
        "items": [
            {
                "id": t.id, "title": t.title, "source": t.source,
                "opportunity_id": t.opportunity_id, "customer_id": t.customer_id,
                "duration_minutes": t.duration_minutes,
                "content": t.content,
                "summary": t.summary,
                "sentiment": t.sentiment,
                "participants": t.participants,
                "keywords_found": json.loads(t.keywords_found) if t.keywords_found else [],
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in items
        ],
        "total": total, "page": page, "page_size": page_size,
        # Audit A-10: standardize on the canonical envelope shape.
        "pages": _math.ceil(total / page_size) if total > 0 else 0,
    }


@router.post("/transcripts/{transcript_id}/summarize")
async def summarize_transcript_endpoint(
    transcript_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Summarize a transcript using AI or rule-based fallback."""
    from app.services.transcript_summarizer import summarize_transcript

    result = await summarize_transcript(db, transcript_id)
    if "error" in result:
        raise NotFoundException(result["error"])
    return result


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


@router.get("/keyword-packs/", response_model=PaginatedResponse[dict])
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


@router.get("/sequences/", response_model=PaginatedResponse[dict])
async def list_sequences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sequences.

    Returns the canonical envelope ``{items, total, page, page_size, pages}``
    so frontend list components don't need a sequence-specific shape
    (audit A-11). The legacy ``sequences`` key is retained for one
    release of back-compat.
    """
    # Round-4 R4-TEN-13 — scope sequences to caller tenant.
    seq_stmt = scoped_for_user(
        select(Sequence).where(Sequence.is_active.is_(True)),
        current_user,
        column=Sequence.tenant_id,
    )
    seqs = (await db.execute(seq_stmt)).scalars().all()
    items = [
        {
            "id": s.id,
            # Round-4 R4-DTO — round-trip tenant_id (R4-TEN-13).
            "tenant_id": getattr(s, "tenant_id", None),
            "name": s.name,
            "description": s.description,
            "steps": json.loads(s.steps_json) if s.steps_json else [],
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in seqs
    ]
    total = len(items)
    return {
        "items": items,
        "total": total,
        "page": 1,
        "page_size": total,
        "pages": 1 if total > 0 else 0,
        # Back-compat key — remove in v1.9.x once frontend has migrated.
        "sequences": items,
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
        # Round-4 R4-TEN-13 — stamp tenant on create.
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    db.add(seq)
    await db.flush()
    await db.refresh(seq)
    return {"id": seq.id, "name": seq.name, "tenant_id": getattr(seq, "tenant_id", None)}


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
    # Round-4 R4-TEN-13 — block cross-tenant enroll on the sequence.
    assert_same_tenant(seq, current_user, exception_cls=NotFoundException)

    enrollment = SequenceEnrollment(
        sequence_id=body.sequence_id,
        opportunity_id=body.opportunity_id,
        customer_id=body.customer_id,
        enrolled_by=current_user.id,
        next_action_at=datetime.now(timezone.utc),
        # Round-4 R4-TEN-13 — stamp tenant on enrollment.
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    db.add(enrollment)
    await db.flush()
    await db.refresh(enrollment)
    return {"id": enrollment.id, "status": enrollment.status, "current_step": enrollment.current_step}


@router.get("/sequences/enrollments")
async def list_enrollments(
    sequence_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List sequence enrollments, optionally filtered by sequence_id."""
    query = select(SequenceEnrollment)
    if sequence_id is not None:
        query = query.where(SequenceEnrollment.sequence_id == sequence_id)
    # Round-4 R4-TEN-13 — scope enrollments to caller tenant.
    query = scoped_for_user(query, current_user, column=SequenceEnrollment.tenant_id)
    result = await db.execute(query.order_by(SequenceEnrollment.created_at.desc()).limit(200))
    enrollments = result.scalars().all()
    return {
        "enrollments": [
            {
                "id": e.id,
                # Round-4 R4-DTO — round-trip tenant_id (R4-TEN-13).
                "tenant_id": getattr(e, "tenant_id", None),
                "sequence_id": e.sequence_id,
                "opportunity_id": e.opportunity_id,
                "customer_id": e.customer_id,
                "lead_id": e.lead_id,
                "current_step": e.current_step,
                "is_paused": e.is_paused,
                "status": e.status,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in enrollments
        ],
    }


@router.patch("/sequences/enrollments/{enrollment_id}/pause")
async def pause_enrollment(
    enrollment_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Pause an enrollment."""
    enrollment = (await db.execute(
        select(SequenceEnrollment).where(SequenceEnrollment.id == enrollment_id)
    )).scalar_one_or_none()
    if not enrollment:
        raise NotFoundException("Kayit bulunamadi")
    # Round-4 R4-TEN-13 — block cross-tenant pause.
    assert_same_tenant(enrollment, current_user, exception_cls=NotFoundException)
    enrollment.is_paused = True
    enrollment.status = "paused"
    await db.flush()
    return {"id": enrollment.id, "is_paused": True, "status": "paused"}


@router.patch("/sequences/enrollments/{enrollment_id}/resume")
async def resume_enrollment(
    enrollment_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_REP, UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Resume a paused enrollment."""
    enrollment = (await db.execute(
        select(SequenceEnrollment).where(SequenceEnrollment.id == enrollment_id)
    )).scalar_one_or_none()
    if not enrollment:
        raise NotFoundException("Kayit bulunamadi")
    # Round-4 R4-TEN-13 — block cross-tenant resume.
    assert_same_tenant(enrollment, current_user, exception_cls=NotFoundException)
    enrollment.is_paused = False
    enrollment.status = "active"
    await db.flush()
    return {"id": enrollment.id, "is_paused": False, "status": "active"}


class SequenceUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[dict] | None = None
    auto_enroll_rules: dict | None = None


# ══════════════════════════════════════════
# SEQUENCES V2 — Step Run Telemetry + Analytics
# (MUST be before /sequences/{sequence_id} to avoid route conflict)
# ══════════════════════════════════════════


@router.get("/sequences/analytics")
async def sequence_analytics(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Sequence-level analytics: completion reasons, touches per target, time to first touch."""
    from app.models.sequence_v2 import SequenceStepRun

    reason_result = await db.execute(
        select(
            SequenceEnrollment.exit_reason,
            func.count(SequenceEnrollment.id),
        )
        .where(SequenceEnrollment.status.in_(["completed", "exited"]))
        .group_by(SequenceEnrollment.exit_reason)
    )
    exit_reasons = {row[0] or "unknown": row[1] for row in reason_result.all()}

    touches_result = await db.execute(
        select(
            SequenceStepRun.enrollment_id,
            func.count(SequenceStepRun.id),
        )
        .where(SequenceStepRun.status == "completed")
        .group_by(SequenceStepRun.enrollment_id)
    )
    touch_counts = [row[1] for row in touches_result.all()]
    avg_touches = sum(touch_counts) / len(touch_counts) if touch_counts else 0

    status_result = await db.execute(
        select(
            SequenceEnrollment.status,
            func.count(SequenceEnrollment.id),
        ).group_by(SequenceEnrollment.status)
    )
    status_dist = {row[0]: row[1] for row in status_result.all()}

    return {
        "exit_reason_distribution": exit_reasons,
        "avg_touches_per_target": round(avg_touches, 1),
        "status_distribution": status_dist,
        "total_step_runs": sum(touch_counts) if touch_counts else 0,
    }


@router.get("/sequences/performance")
async def sequence_performance(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Per-sequence funnel: enrollment counts by status + avg completed step runs per enrollment."""
    from app.models.sequence_v2 import SequenceStepRun

    seq_rows = (await db.execute(select(Sequence.id, Sequence.name, Sequence.is_active))).all()

    enroll_rows = (
        await db.execute(
            select(
                SequenceEnrollment.sequence_id,
                func.count(SequenceEnrollment.id).label("total"),
                func.count().filter(SequenceEnrollment.status == "active").label("active_n"),
                func.count().filter(SequenceEnrollment.status == "completed").label("completed_n"),
                func.count().filter(SequenceEnrollment.status == "exited").label("exited_n"),
                func.count().filter(SequenceEnrollment.status == "paused").label("paused_n"),
                func.count().filter(SequenceEnrollment.status == "cancelled").label("cancelled_n"),
            ).group_by(SequenceEnrollment.sequence_id)
        )
    ).all()
    by_seq = {int(row.sequence_id): row for row in enroll_rows}

    per_enrollment = (
        select(
            SequenceStepRun.sequence_id,
            SequenceStepRun.enrollment_id,
            func.count(SequenceStepRun.id).label("completed_steps"),
        )
        .where(SequenceStepRun.status == "completed")
        .group_by(SequenceStepRun.sequence_id, SequenceStepRun.enrollment_id)
    ).subquery()

    avg_rows = (
        await db.execute(
            select(per_enrollment.c.sequence_id, func.avg(per_enrollment.c.completed_steps)).group_by(
                per_enrollment.c.sequence_id
            )
        )
    ).all()
    avg_by_seq = {int(row[0]): float(row[1] or 0) for row in avg_rows}

    sequences_out: list[dict] = []
    total_enrollments = 0
    for sid, name, is_active in seq_rows:
        agg = by_seq.get(int(sid))
        et = int(agg.total) if agg is not None else 0
        total_enrollments += et
        sequences_out.append(
            {
                "sequence_id": int(sid),
                "name": name,
                "is_active": bool(is_active),
                "enrollments_total": et,
                "enrollments_active": int(agg.active_n) if agg is not None else 0,
                "enrollments_completed": int(agg.completed_n) if agg is not None else 0,
                "enrollments_exited": int(agg.exited_n) if agg is not None else 0,
                "enrollments_paused": int(agg.paused_n) if agg is not None else 0,
                "enrollments_cancelled": int(agg.cancelled_n) if agg is not None else 0,
                "avg_completed_steps_per_enrollment": round(avg_by_seq.get(int(sid), 0.0), 2),
            }
        )

    return {
        "sequences": sequences_out,
        "rollup": {
            "sequence_count": len(sequences_out),
            "enrollment_count": total_enrollments,
        },
    }


@router.get("/sequences/variant-metrics")
async def variant_metrics(
    sequence_id: int | None = None,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """A/B variant performance metrics — aggregated by variant key per step."""
    from app.models.sequence_v2 import SequenceStepRun

    query = select(
        SequenceStepRun.sequence_id,
        SequenceStepRun.step_number,
        SequenceStepRun.variant_key,
        func.count(SequenceStepRun.id).label("total"),
        func.count().filter(SequenceStepRun.status == "completed").label("completed"),
        func.count().filter(SequenceStepRun.status == "failed").label("failed"),
    ).where(
        SequenceStepRun.variant_key.isnot(None),
    ).group_by(
        SequenceStepRun.sequence_id,
        SequenceStepRun.step_number,
        SequenceStepRun.variant_key,
    ).order_by(
        SequenceStepRun.sequence_id,
        SequenceStepRun.step_number,
    )

    if sequence_id:
        query = query.where(SequenceStepRun.sequence_id == sequence_id)

    rows = (await db.execute(query)).all()
    return {
        "variants": [
            {
                "sequence_id": row[0],
                "step_number": row[1],
                "variant_key": row[2],
                "total": row[3],
                "completed": row[4],
                "failed": row[5],
            }
            for row in rows
        ],
    }


@router.get("/sequences/domain-events")
async def list_domain_events(
    event_type: str | None = None,
    limit: int = Query(default=50, le=200),
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """List recent domain events (audit/debugging)."""
    from app.models.sequence_v2 import DomainEvent

    query = select(DomainEvent).order_by(DomainEvent.created_at.desc()).limit(limit)
    if event_type:
        query = query.where(DomainEvent.event_type == event_type)

    events = (await db.execute(query)).scalars().all()
    return {
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "payload": json.loads(e.payload_json) if e.payload_json else None,
                "actor_id": e.actor_id,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ],
    }


@router.get("/sequences/enrollments/{enrollment_id}/detail")
async def get_enrollment_detail(
    enrollment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get detailed enrollment info including v2 fields and step runs."""
    from app.models.sequence_v2 import SequenceStepRun

    enrollment = (
        await db.execute(
            select(SequenceEnrollment).where(SequenceEnrollment.id == enrollment_id)
        )
    ).scalar_one_or_none()
    if not enrollment:
        raise NotFoundException("Enrollment bulunamadi")

    seq = (
        await db.execute(select(Sequence).where(Sequence.id == enrollment.sequence_id))
    ).scalar_one_or_none()

    step_runs_result = await db.execute(
        select(SequenceStepRun)
        .where(SequenceStepRun.enrollment_id == enrollment_id)
        .order_by(SequenceStepRun.step_number.asc())
    )
    step_runs = step_runs_result.scalars().all()

    return {
        "enrollment": {
            "id": enrollment.id,
            "sequence_id": enrollment.sequence_id,
            "sequence_name": seq.name if seq else None,
            "opportunity_id": enrollment.opportunity_id,
            "customer_id": enrollment.customer_id,
            "lead_id": enrollment.lead_id,
            "current_step": enrollment.current_step,
            "status": enrollment.status,
            "is_paused": enrollment.is_paused,
            "exit_reason": enrollment.exit_reason,
            "completed_at": enrollment.completed_at.isoformat() if enrollment.completed_at else None,
            "next_action_at": enrollment.next_action_at.isoformat() if enrollment.next_action_at else None,
            "created_at": enrollment.created_at.isoformat() if enrollment.created_at else None,
        },
        "step_runs": [
            {
                "id": sr.id,
                "step_number": sr.step_number,
                "step_action": sr.step_action,
                "variant_key": sr.variant_key,
                "status": sr.status,
                "reason_codes": json.loads(sr.reason_codes) if sr.reason_codes else [],
                "started_at": sr.started_at.isoformat() if sr.started_at else None,
                "completed_at": sr.completed_at.isoformat() if sr.completed_at else None,
            }
            for sr in step_runs
        ],
        "total_steps": len(json.loads(seq.steps_json)) if seq and seq.steps_json else 0,
    }


@router.get("/sequences/enrollments/{enrollment_id}/step-runs")
async def list_step_runs(
    enrollment_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all step run records for an enrollment (telemetry)."""
    from app.models.sequence_v2 import SequenceStepRun

    runs = (
        await db.execute(
            select(SequenceStepRun)
            .where(SequenceStepRun.enrollment_id == enrollment_id)
            .order_by(SequenceStepRun.step_number.asc())
        )
    ).scalars().all()

    return {
        "enrollment_id": enrollment_id,
        "step_runs": [
            {
                "id": r.id,
                "step_number": r.step_number,
                "step_action": r.step_action,
                "variant_key": r.variant_key,
                "status": r.status,
                "reason_codes": json.loads(r.reason_codes) if r.reason_codes else [],
                "payload_snapshot": json.loads(r.payload_snapshot) if r.payload_snapshot else None,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            }
            for r in runs
        ],
    }


@router.get("/sequences/{sequence_id}")
async def get_sequence(
    sequence_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single sequence by ID."""
    seq = (await db.execute(select(Sequence).where(Sequence.id == sequence_id))).scalar_one_or_none()
    if not seq:
        raise NotFoundException("Sekans bulunamadi")
    # Round-4 R4-TEN-13 — block cross-tenant read.
    assert_same_tenant(seq, current_user, exception_cls=NotFoundException)
    return {
        "id": seq.id,
        # Round-4 R4-DTO — round-trip tenant_id (R4-TEN-13).
        "tenant_id": getattr(seq, "tenant_id", None),
        "name": seq.name,
        "description": seq.description,
        "steps": json.loads(seq.steps_json) if seq.steps_json else [],
        "auto_enroll_rules": json.loads(seq.auto_enroll_rules_json) if seq.auto_enroll_rules_json else None,
        "created_at": seq.created_at.isoformat() if seq.created_at else None,
    }


@router.patch("/sequences/{sequence_id}")
async def update_sequence(
    sequence_id: int,
    body: SequenceUpdate,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Update an existing sequence."""
    seq = (await db.execute(select(Sequence).where(Sequence.id == sequence_id))).scalar_one_or_none()
    if not seq:
        raise NotFoundException("Sekans bulunamadi")
    # Round-4 R4-TEN-13 — block cross-tenant update.
    assert_same_tenant(seq, current_user, exception_cls=NotFoundException)

    if body.name is not None:
        seq.name = body.name
    if body.description is not None:
        seq.description = body.description
    if body.steps is not None:
        seq.steps_json = json.dumps(body.steps, ensure_ascii=False)
    if body.auto_enroll_rules is not None:
        seq.auto_enroll_rules_json = json.dumps(body.auto_enroll_rules, ensure_ascii=False)

    await db.flush()
    await db.refresh(seq)
    return {
        "id": seq.id,
        # Round-4 R4-DTO — round-trip tenant_id (R4-TEN-13).
        "tenant_id": getattr(seq, "tenant_id", None),
        "name": seq.name,
        "description": seq.description,
        "steps": json.loads(seq.steps_json) if seq.steps_json else [],
        "auto_enroll_rules": json.loads(seq.auto_enroll_rules_json) if seq.auto_enroll_rules_json else None,
    }


@router.post("/sequences/{sequence_id}/auto-enroll")
async def auto_enroll_sequence(
    sequence_id: int,
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
    db: AsyncSession = Depends(get_db),
):
    """Run auto-enrollment rules for a sequence against all leads not yet enrolled.

    Reads auto_enroll_rules_json from the sequence and enrolls matching leads
    that do not already have an active or completed enrollment.
    """
    from app.models.lead import Lead

    seq = (await db.execute(select(Sequence).where(Sequence.id == sequence_id))).scalar_one_or_none()
    if not seq:
        raise NotFoundException("Sekans bulunamadi")
    # Round-4 R4-TEN-13 — block cross-tenant auto-enroll trigger.
    assert_same_tenant(seq, current_user, exception_cls=NotFoundException)

    rules = json.loads(seq.auto_enroll_rules_json) if seq.auto_enroll_rules_json else []
    if not rules:
        return {"enrolled": 0, "message": "Auto-enrollment rules not configured for this sequence"}

    # Fetch leads not yet enrolled in this sequence
    already_enrolled_result = await db.execute(
        select(SequenceEnrollment.lead_id).where(
            SequenceEnrollment.sequence_id == sequence_id,
            SequenceEnrollment.lead_id.isnot(None),
            SequenceEnrollment.status.in_(["active", "paused", "completed"]),
        )
    )
    already_enrolled_ids = {row[0] for row in already_enrolled_result.all()}

    # Apply simple rule matching against Lead fields (exclude converted/closed leads).
    # Round-4 R4-TEN-13 — restrict candidate leads to caller tenant.
    lead_query = scoped_for_user(
        select(Lead).where(Lead.status.notin_(["converted", "lost", "cancelled"])),
        current_user,
        column=Lead.tenant_id,
    )
    leads_result = await db.execute(lead_query.limit(500))
    leads = leads_result.scalars().all()

    enrolled_count = 0
    for lead in leads:
        if lead.id in already_enrolled_ids:
            continue
        if _lead_matches_rules(lead, rules):
            enrollment = SequenceEnrollment(
                sequence_id=sequence_id,
                lead_id=lead.id,
                enrolled_by=current_user.id,
                next_action_at=datetime.now(timezone.utc),
                # Round-4 R4-TEN-13 — stamp tenant on auto-enrolled rows.
                tenant_id=getattr(current_user, "tenant_id", None),
            )
            db.add(enrollment)
            enrolled_count += 1

    if enrolled_count > 0:
        await db.flush()

    return {
        "sequence_id": sequence_id,
        "enrolled": enrolled_count,
        "message": f"{enrolled_count} leads enrolled via auto-enrollment rules",
    }


def _lead_matches_rules(lead, rules: list[dict]) -> bool:
    """Check if a lead matches all auto-enrollment rules (AND logic)."""
    for rule in rules:
        field = rule.get("field", "")
        op = rule.get("op", "")
        value = rule.get("value", "")
        if not hasattr(lead, field):
            continue
        field_val = getattr(lead, field)
        if op == "equals" and str(field_val) != str(value):
            return False
        elif op == "contains" and value.lower() not in str(field_val or "").lower():
            return False
        elif op == "not_empty" and not field_val:
            return False
        elif op == "gte":
            try:
                if float(field_val or 0) < float(value):
                    return False
            except (TypeError, ValueError):
                return False
    return True


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
    # Round-4 R4-TEN-13 — scope segments to caller tenant.
    seg_stmt = scoped_for_user(
        select(Segment).order_by(Segment.name),
        current_user,
        column=Segment.tenant_id,
    )
    segs = (await db.execute(seg_stmt)).scalars().all()
    return {
        "segments": [
            {"id": s.id,
             # Round-4 R4-DTO — round-trip tenant_id (R4-TEN-13).
             "tenant_id": getattr(s, "tenant_id", None),
             "name": s.name, "description": s.description,
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
        # Round-4 R4-TEN-13 — stamp tenant on segment create.
        tenant_id=getattr(current_user, "tenant_id", None),
    )
    db.add(seg)
    await db.flush()
    await db.refresh(seg)
    return {
        "id": seg.id,
        # Round-4 R4-DTO — round-trip tenant_id (R4-TEN-13).
        "tenant_id": getattr(seg, "tenant_id", None),
        "name": seg.name,
        "customer_count": count,
    }


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
    # Round-4 R4-TEN-13 — block cross-tenant segment read.
    assert_same_tenant(seg, current_user, exception_cls=NotFoundException)

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
    - contains, equals, not_equals, not_empty, gte, lte, in, starts_with

    Advanced:
    - or_group: array of sub-rules, ANY must match (OR logic)
    - weight: optional numeric weight per rule for scoring (0-100)

    Aggregate operators (cross-table):
    - quote_count_gte, quote_value_gte, last_quote_within_days
    """
    from datetime import timedelta

    query = select(Customer)
    aggregate_filters = []
    weighted_rules = []  # (rule, weight) pairs for scoring

    for rule in rules:
        weight = rule.get("weight")
        if weight is not None:
            weighted_rules.append((rule, float(weight)))

        # OR group: any sub-rule matches
        if rule.get("op") == "or_group" and isinstance(rule.get("rules"), list):
            or_conditions = []
            for sub_rule in rule["rules"]:
                sub_field = sub_rule.get("field", "")
                sub_op = sub_rule.get("op", "")
                sub_val = sub_rule.get("value", "")
                if hasattr(Customer, sub_field):
                    col = getattr(Customer, sub_field)
                    if sub_op == "contains":
                        safe = str(sub_val).replace("%", "\\%").replace("_", "\\_")
                        or_conditions.append(col.ilike(f"%{safe}%"))
                    elif sub_op == "equals":
                        or_conditions.append(col == sub_val)
                    elif sub_op == "not_empty":
                        or_conditions.append(and_(col.isnot(None), col != ""))
            if or_conditions:
                query = query.where(or_(*or_conditions))
            continue
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


# ── Backward-compatible legacy mount ─────────────────────────────────────────
# Must run AFTER every @router.<verb> decorator above so the snapshot of
# `router.routes` taken by `include_router` is complete.
legacy_router.include_router(router)
