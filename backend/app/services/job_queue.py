"""Async job queue — Redis/arq removed, runs inline.

Handles: sequence step execution, PDF generation, email sending.

Originally backed by arq + Redis with retry/dead-letter/job-monitoring.
After the Redis removal we run jobs **inline** in the calling request:
the caller awaits the job function instead of enqueueing. The
``execute_sequence_step`` and ``generate_pdf_job`` bodies are
unchanged so any Redis-equivalent we wire in later can pick them up
via the ``WorkerSettings`` registry below.

Tradeoff vs. arq:
- No background isolation: a failing job surfaces inside the request
  that triggered it (good for visibility, bad for latency on slow jobs
  like PDF generation). PDF generation is already wrapped in a
  timeout in ``quote_service`` so the worst case is bounded.
- No retries: a transient failure isn't auto-retried. Sequence steps
  reschedule themselves via ``next_action_at`` so this is OK; PDF
  generation surfaces an error to the user, who can retry.
- Single-worker scope: the v2 sequence engine's ``StepRun``
  unique-constraint still prevents double execution within the same
  worker, but multi-worker installs lose cross-worker dedupe.
"""

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


# ── Job Functions ──

async def execute_sequence_step(ctx: dict, enrollment_id: int) -> str:
    """Execute the next step in a sequence enrollment.

    Called by arq worker with retry support.
    When FEATURE_SEQUENCES_V2 is on, delegates to the v2 engine which adds:
    - Idempotency (StepRun unique constraint prevents double execution)
    - Global exit conditions (lead converted, opp closed, etc.)
    - Telemetry (SequenceStepRun record per execution)
    - Domain events (sequence.step_completed, sequence.completed, sequence.exited)
    """
    from sqlalchemy import select
    from app.core.database import async_session
    from app.core.config import settings as app_settings
    from app.models.engagement import SequenceEnrollment, Sequence
    from app.services.dedupe_service import upsert_task

    async with async_session() as db:
        enrollment = (await db.execute(
            select(SequenceEnrollment).where(SequenceEnrollment.id == enrollment_id)
        )).scalar_one_or_none()
        if not enrollment or enrollment.status != "active":
            return f"Enrollment {enrollment_id} not active"

        # ── V2 engine (feature-flagged) ──
        if app_settings.FEATURE_SEQUENCES_V2:
            from app.services.sequence_engine import execute_step_v2

            result = await execute_step_v2(db, enrollment)
            await db.commit()
            return result

        # ── V1 fallback (original logic, untouched) ──
        seq = (await db.execute(
            select(Sequence).where(Sequence.id == enrollment.sequence_id)
        )).scalar_one_or_none()
        if not seq:
            return f"Sequence not found"

        steps = json.loads(seq.steps_json) if seq.steps_json else []
        current = enrollment.current_step
        if current > len(steps):
            # ``exit_reason`` was a typed nullable column the analytics
            # endpoint already aggregates over (engagement.py:456-460)
            # but no writer ever populated it on the natural-completion
            # path, so the dashboard always saw "unknown". Stamp the
            # canonical reason here so the funnel report is meaningful.
            enrollment.status = "completed"
            enrollment.exit_reason = "all_steps_completed"
            await db.commit()
            return f"Sequence completed for enrollment {enrollment_id}"

        step = steps[current - 1]
        action = step.get("action", "task")
        template = step.get("template", "")

        # Execute step
        if action == "task":
            await upsert_task(
                db,
                owner_id=enrollment.enrolled_by or 1,
                opportunity_id=enrollment.opportunity_id,
                title=(template or f"Sira adimi {current}")[:255],
                source="rule",
                priority="normal",
                status="open",
                dedupe_window_days=14,
            )

        # Advance to next step
        enrollment.current_step = current + 1
        if enrollment.current_step > len(steps):
            enrollment.status = "completed"
            enrollment.exit_reason = "all_steps_completed"
        else:
            next_delay = steps[current].get("delay_days", 1) if current < len(steps) else 0
            enrollment.next_action_at = datetime.now(timezone.utc) + timedelta(days=next_delay)

        await db.commit()
        return f"Step {current} executed for enrollment {enrollment_id}"


async def generate_pdf_job(ctx: dict, quote_id: int, user_id: int) -> str:
    """Background PDF generation job."""
    from app.core.database import async_session
    from app.services.quote_generator import generate_quote_pdf
    from app.services.quote_service import QuoteService
    from sqlalchemy import select
    from app.models.quote import Quote

    async with async_session() as db:
        quote = (await db.execute(select(Quote).where(Quote.id == quote_id))).scalar_one_or_none()
        if not quote:
            return f"Quote {quote_id} not found"

        service = QuoteService(db)
        quote_data = await service._build_quote_data(quote, user_id)
        pdf_path = await generate_quote_pdf(quote_data, quote.language)
        quote.pdf_path = pdf_path
        await db.commit()
        return f"PDF generated: {pdf_path}"


# ── Worker registry (preserved so a future Redis-equivalent can re-register) ──


async def startup(ctx: dict) -> None:
    """No-op startup hook — kept for symmetry with the worker contract."""
    logger.info("Inline job runner active (no background worker)")


async def shutdown(ctx: dict) -> None:
    """No-op shutdown hook — kept for symmetry with the worker contract."""
    return None


class WorkerSettings:
    """Job function registry. Background-worker fields removed; if a
    Redis-equivalent is reintroduced (e.g. arq, dramatiq, RQ), this
    class is the canonical list of function objects to wire in."""

    functions = [execute_sequence_step, generate_pdf_job]
    on_startup = startup
    on_shutdown = shutdown


# ── Enqueue Helper (inline) ──

# Static dispatch table mirroring ``WorkerSettings.functions`` so
# ``enqueue_job`` can resolve a name → callable without importing the
# functions twice.
_FUNCTION_MAP = {
    "execute_sequence_step": execute_sequence_step,
    "generate_pdf_job": generate_pdf_job,
}


async def enqueue_job(function_name: str, *args, **kwargs) -> bool:
    """Run the named job inline.

    Pre-Redis-removal this would push to arq; now it ``await``s the
    function directly. The signature still returns ``bool`` so callers
    don't need to change. ``True`` = job ran without raising;
    ``False`` = job raised (already logged).
    """
    func = _FUNCTION_MAP.get(function_name)
    if func is None:
        logger.error("Unknown job function: %s", function_name)
        return False
    try:
        await func({}, *args, **kwargs)
        return True
    except Exception as exc:
        logger.error("Inline job execution failed (%s): %s", function_name, exc)
        return False
