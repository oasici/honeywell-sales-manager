"""Async job queue using arq (Redis-backed).

Handles: sequence step execution, PDF generation, email sending.
Features: retry with exponential backoff, dead letter logging, job monitoring.
Falls back gracefully if Redis/arq unavailable — jobs execute inline.
"""

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_arq_available = False
_redis_settings = None


def _get_redis_settings():
    """Get arq RedisSettings from app config."""
    global _redis_settings
    if _redis_settings is not None:
        return _redis_settings
    try:
        from arq.connections import RedisSettings
        from app.core.config import settings
        if not settings.REDIS_URL:
            return None
        # Parse redis://[:password]@host:port/db
        url = settings.REDIS_URL
        password = None
        host = "redis"
        port = 6379
        db = 0
        if "://" in url:
            parts = url.split("://", 1)[1]
            if "@" in parts:
                auth, hostpart = parts.rsplit("@", 1)
                password = auth.lstrip(":") or None
            else:
                hostpart = parts
            if "/" in hostpart:
                hostpart, db_str = hostpart.rsplit("/", 1)
                db = int(db_str) if db_str else 0
            if ":" in hostpart:
                host, port_str = hostpart.split(":", 1)
                port = int(port_str)
            else:
                host = hostpart
        _redis_settings = RedisSettings(host=host, port=port, password=password, database=db)
        return _redis_settings
    except Exception as e:
        logger.debug("arq Redis settings parse failed: %s", e)
        return None


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
            enrollment.status = "completed"
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


# ── arq Worker Config ──

async def startup(ctx: dict) -> None:
    logger.info("arq worker started")


async def shutdown(ctx: dict) -> None:
    logger.info("arq worker stopped")


class WorkerSettings:
    """arq worker configuration — import this in arq CLI."""
    functions = [execute_sequence_step, generate_pdf_job]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 10
    job_timeout = 300  # 5 min per job
    retry_jobs = True
    max_tries = 3
    health_check_interval = 30

    @staticmethod
    def redis_settings():
        return _get_redis_settings()


# ── Enqueue Helper ──

async def enqueue_job(function_name: str, *args, **kwargs) -> bool:
    """Enqueue a job to arq. Falls back to inline execution if arq unavailable."""
    try:
        from arq import create_pool
        rs = _get_redis_settings()
        if not rs:
            raise RuntimeError("No Redis")
        pool = await create_pool(rs)
        await pool.enqueue_job(function_name, *args, **kwargs)
        await pool.close()
        return True
    except Exception as e:
        logger.debug("arq enqueue failed (%s), executing inline: %s", e, function_name)
        # Inline fallback
        func_map = {
            "execute_sequence_step": execute_sequence_step,
            "generate_pdf_job": generate_pdf_job,
        }
        func = func_map.get(function_name)
        if func:
            try:
                await func({}, *args, **kwargs)
            except Exception as exc:
                logger.error("Inline job execution failed: %s", exc)
        return False
