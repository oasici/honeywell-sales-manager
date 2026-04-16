from __future__ import annotations

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

import sqlalchemy

from app.api.v1.router import v1_router
from app.core.config import settings
from app.core.database import async_session, engine
from app.core.error_tracking import init_sentry
from app.core.logging_config import setup_logging, request_id_var
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.core.exceptions import AppException, app_exception_handler, unhandled_exception_handler
from app.core.middleware import (
    AuditLogMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.models import *  # noqa: F401, F403

setup_logging(settings.ENV)
logger = logging.getLogger(__name__)

_start_time = time.time()

# ── Rate limiter (shared instance) ──
from app.core.rate_limit import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Async lifespan: startup and shutdown logic."""
    init_sentry(dsn=os.environ.get("SENTRY_DSN"), env=settings.ENV)

    from app.core.database import Base

    _is_postgres = settings.DATABASE_URL.startswith("postgresql")

    # Create tables — checkfirst=True prevents UniqueViolationError on existing DBs
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created / verified")
    except Exception as e:
        # Tables may already exist with conflicting types — safe to continue
        logger.warning("create_all partial: %s", str(e)[:200])

    # PostgreSQL-only extensions and indexes (silent fail on SQLite)
    # Auto-sync schema: add missing columns to existing tables
    # This handles Render where tables were created by an older version
    if _is_postgres:
        try:
            async with engine.begin() as conn:
                # Get all model tables and their columns from SQLAlchemy metadata
                for table in Base.metadata.sorted_tables:
                    for column in table.columns:
                        col_name = column.name
                        # Determine SQL type
                        col_type = column.type.compile(engine.dialect)
                        nullable = "NULL" if column.nullable else "NOT NULL"
                        default = ""
                        if column.default is not None and column.default.arg is not None:
                            dval = column.default.arg
                            if isinstance(dval, bool):
                                default = f" DEFAULT {'true' if dval else 'false'}"
                            elif isinstance(dval, (int, float)):
                                default = f" DEFAULT {dval}"
                            elif isinstance(dval, str):
                                default = f" DEFAULT '{dval}'"
                        sql = f"ALTER TABLE {table.name} ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default}"
                        try:
                            await conn.execute(sqlalchemy.text(sql))
                        except Exception:
                            pass  # Column exists or type conflict — safe to skip
            logger.info("Schema auto-sync completed")
        except Exception as e:
            logger.warning("Schema auto-sync failed: %s", str(e)[:200])

    _pg_migrations = [
        "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        "CREATE INDEX IF NOT EXISTS ix_transcripts_content_trgm ON transcripts USING gin (content gin_trgm_ops)",
        "CREATE INDEX IF NOT EXISTS ix_transcripts_title_trgm ON transcripts USING gin (title gin_trgm_ops)",
    ]
    for sql in _pg_migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(sqlalchemy.text(sql))
        except Exception as e:
            logger.debug("PG migration skipped (N/A): %s", str(e)[:100])
    logger.info("Database migration completed")

    # Warn if ENCRYPTION_KEY not set (required for field-level encryption)
    if not os.environ.get("ENCRYPTION_KEY"):
        logger.warning("ENCRYPTION_KEY not set — field-level encryption disabled")

    for dir_path in [settings.QUOTES_DIR, settings.UPLOADS_DIR]:
        os.makedirs(dir_path, exist_ok=True)

    try:
        from app.services.auth_service import create_default_admin
        async with async_session() as db:
            await create_default_admin(db)
    except Exception as exc:
        logger.error("Default admin creation failed: %s", exc)

    # Scheduler: only start if SCHEDULER_ENABLED=true (separate process in production)
    scheduler_enabled = os.environ.get("SCHEDULER_ENABLED", "false").lower() == "true"
    if scheduler_enabled:
        try:
            start_scheduler()
            logger.info("Scheduler started (in-process mode)")
        except Exception as exc:
            logger.warning("Scheduler start failed (non-critical): %s", exc)
    else:
        logger.info("Scheduler disabled")

    # Start audit buffer flush task
    try:
        from app.core.audit_buffer import start_audit_buffer, stop_audit_buffer
        start_audit_buffer()
    except Exception as exc:
        logger.warning("Audit buffer start failed (non-critical): %s", exc)

    # Wire event bus → webhook service (LIVE delivery)
    try:
        from app.core.event_bus import event_bus
        from app.services.webhook_service import WebhookService

        _webhook_service = WebhookService(db_session_factory=async_session)
        event_bus.subscribe("quote.approved", _webhook_service.handle_event)
        event_bus.subscribe("quote.sent", _webhook_service.handle_event)
        event_bus.subscribe("opportunity.created", _webhook_service.handle_event)
        event_bus.subscribe("opportunity.stage_changed", _webhook_service.handle_event)
        event_bus.subscribe("lead.converted", _webhook_service.handle_event)
        event_bus.subscribe("customer.created", _webhook_service.handle_event)
        event_bus.subscribe("email.parsed", _webhook_service.handle_event)
        # Campaign member conversion tracking
        if settings.FEATURE_CAMPAIGNS:
            async def _update_campaign_on_lead_convert(event_type: str, event_data: dict):
                try:
                    async with async_session() as session:
                        from app.models.campaign import CampaignMember
                        lead_id = event_data.get("lead_id")
                        if lead_id:
                            result = await session.execute(
                                sqlalchemy.select(CampaignMember).where(
                                    CampaignMember.lead_id == lead_id
                                )
                            )
                            for member in result.scalars().all():
                                member.status = "converted"
                            await session.commit()
                except Exception as exc:
                    logger.warning("Campaign member conversion update failed: %s", exc)

            event_bus.subscribe("lead.converted", _update_campaign_on_lead_convert)
            logger.info("Campaign conversion handler wired")

        # Invoice payment tracking
        if settings.FEATURE_INVOICING:
            async def _on_invoice_paid(event_type: str, event_data: dict):
                # Placeholder: could update contract actual_revenue or trigger rev-rec
                pass

            event_bus.subscribe("invoice.paid", _on_invoice_paid)
            logger.info("Invoice payment handler wired")

        # Wire Revenue Signal handlers (event → canonical signal stream)
        if settings.FEATURE_REVENUE_COCKPIT:
            from app.services.revenue_signal_handler import RevenueSignalHandler
            _rs_handler = RevenueSignalHandler(session_factory=async_session)
            event_bus.subscribe("email.parsed", _rs_handler.on_email_parsed)
            event_bus.subscribe("opportunity.created", _rs_handler.on_opportunity_created)
            event_bus.subscribe("opportunity.stage_changed", _rs_handler.on_stage_changed)
            event_bus.subscribe("quote.approved", _rs_handler.on_quote_event)
            event_bus.subscribe("quote.sent", _rs_handler.on_quote_event)
            event_bus.subscribe("lead.converted", _rs_handler.on_lead_converted)
            logger.info("Revenue signal handlers wired")

        # Wire playbook evaluation to revenue signals
        if settings.FEATURE_REVENUE_COCKPIT:
            async def _on_revenue_signal_created(event_type: str, payload: dict):
                try:
                    async with async_session() as sig_db:
                        from app.services.playbook_service import PlaybookService
                        from app.models.revenue_signal import RevenueSignal

                        signal_id = payload.get("signal_id")
                        if signal_id:
                            signal = (
                                await sig_db.execute(
                                    sqlalchemy.select(RevenueSignal).where(
                                        RevenueSignal.id == signal_id
                                    )
                                )
                            ).scalar_one_or_none()
                            if signal:
                                service = PlaybookService(sig_db)
                                await service.evaluate_signal(signal)
                                await sig_db.commit()
                except Exception as exc:
                    logger.warning("Playbook auto-trigger failed: %s", exc)

            event_bus.subscribe(
                "revenue_signal.created", _on_revenue_signal_created,
            )

        # Wire workflow rules engine to common events
        if settings.FEATURE_WORKFLOW_RULES:
            from app.services.workflow_service import WorkflowService

            async def _on_workflow_event(event_type: str, payload: dict):
                try:
                    async with async_session() as wf_db:
                        svc = WorkflowService(wf_db)
                        event_map = {
                            "opportunity.stage_changed": ("opportunity", "stage_changed"),
                            "quote.approved": ("quote", "approved"),
                            "email.parsed": ("email", "parsed"),
                        }
                        mapping = event_map.get(event_type)
                        if mapping:
                            await svc.evaluate_event(
                                mapping[0], mapping[1], payload,
                            )
                            await wf_db.commit()
                except Exception as exc:
                    logger.warning("Workflow rule eval failed: %s", exc)

            event_bus.subscribe("opportunity.stage_changed", _on_workflow_event)
            event_bus.subscribe("quote.approved", _on_workflow_event)
            event_bus.subscribe("email.parsed", _on_workflow_event)
            logger.info("Workflow rules engine wired")

        # Wire Sequence V2 events → workflow rules + logging
        if settings.FEATURE_SEQUENCES_V2:
            from app.services.domain_events import DomainEvents

            async def _on_sequence_event(event_type: str, payload: dict):
                """Route sequence lifecycle events to workflow rules engine."""
                try:
                    if settings.FEATURE_WORKFLOW_RULES:
                        async with async_session() as wf_db:
                            svc = WorkflowService(wf_db)
                            await svc.evaluate_event(
                                "sequence", event_type.split(".")[-1], payload,
                            )
                            await wf_db.commit()
                except Exception as exc:
                    logger.warning("Sequence event → workflow rule eval failed: %s", exc)

            event_bus.subscribe(DomainEvents.SEQUENCE_STEP_COMPLETED, _on_sequence_event)
            event_bus.subscribe(DomainEvents.SEQUENCE_COMPLETED, _on_sequence_event)
            event_bus.subscribe(DomainEvents.SEQUENCE_EXITED, _on_sequence_event)
            logger.info("Sequence V2 event handlers wired")

        # Wire behavioral scoring event handlers
        if settings.FEATURE_BEHAVIORAL_SCORING:
            from app.services.scoring_service import (
                on_sequence_step_completed as _scoring_on_step,
                on_sequence_exited as _scoring_on_exit,
            )
            from app.services.domain_events import DomainEvents as _DE

            event_bus.subscribe(_DE.SEQUENCE_STEP_COMPLETED, _scoring_on_step)
            event_bus.subscribe(_DE.SEQUENCE_EXITED, _scoring_on_exit)
            logger.info("Behavioral scoring event handlers wired")

        # Slack/Teams notifications
        if settings.SLACK_WEBHOOK_URL or settings.TEAMS_WEBHOOK_URL:
            from app.services.notification_channel_service import NotificationChannelService

            async def _on_slack_teams_event(event_type: str, payload: dict):
                try:
                    ncs = NotificationChannelService()
                    if event_type == "opportunity.stage_changed":
                        msg = ncs.format_opportunity_card(payload)
                    elif event_type.startswith("quote."):
                        msg = ncs.format_quote_card(payload)
                    else:
                        return
                    if settings.SLACK_WEBHOOK_URL:
                        await ncs.send_slack(settings.SLACK_WEBHOOK_URL, msg)
                    if settings.TEAMS_WEBHOOK_URL:
                        await ncs.send_teams(settings.TEAMS_WEBHOOK_URL, msg)
                except Exception as exc:
                    logger.warning("Slack/Teams bildirimi gonderilemedi: %s", exc)

            for evt in [
                "opportunity.stage_changed",
                "opportunity.created",
                "quote.approved",
                "quote.sent",
            ]:
                event_bus.subscribe(evt, _on_slack_teams_event)
            logger.info("Slack/Teams bildirim isleyicileri baglandi")

        logger.info("Event bus wired: %d handlers registered", event_bus.handler_count)
    except Exception as exc:
        logger.warning("Event bus wiring failed (non-critical): %s", exc)

    # Pre-load embedding model if RAG enabled (avoids cold start on first request)
    if settings.FEATURE_RAG:
        try:
            from app.services.vector_store import _get_embedding_model

            _get_embedding_model()
            logger.info("Embedding model pre-loaded for RAG")
        except Exception as exc:
            logger.warning("Embedding model pre-load failed (non-critical): %s", exc)

    logger.info("Application started (env=%s, workers=gunicorn)", settings.ENV)

    yield

    if scheduler_enabled:
        stop_scheduler()
    # Flush remaining audit entries
    await stop_audit_buffer()
    # Close Redis connection pool
    from app.core.redis_client import close_redis
    await close_redis()
    await engine.dispose()
    logger.info("Application stopped")


app = FastAPI(
    title="Honeywell Sales Manager API",
    description="Backend API for Honeywell Turkey spare-parts sales management",
    version="1.0.0",
    lifespan=lifespan,
    redirect_slashes=False,
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
    openapi_url=None if settings.is_production else "/openapi.json",
)

# ── Rate limiter state ──
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Request ID middleware ──
class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to each request for log correlation."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_var.set(rid)
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response


# ── Middleware (order matters: last added = first executed) ──

# 0. Request ID tracking (outermost — runs first)
app.add_middleware(RequestIDMiddleware)

# 1. Security headers on all responses
app.add_middleware(SecurityHeadersMiddleware)

# 2. Audit logging for state-changing requests
app.add_middleware(AuditLogMiddleware)

# 3. Request size limit
app.add_middleware(RequestSizeLimitMiddleware, max_size_mb=settings.MAX_UPLOAD_SIZE_MB)

# 4. CORS — restricted origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token"],
    expose_headers=["X-CSRF-Token"],
)

# ── Exception handlers ──
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# ── Routers ──
app.include_router(v1_router, prefix="/api/v1")


@app.get("/api/debug/login-test")
async def debug_login_test():
    """Debug endpoint to test login flow."""
    import traceback
    results: dict[str, str] = {}
    try:
        from app.services.auth_service import authenticate
        results["auth_import"] = "ok"
    except Exception as e:
        results["auth_import"] = f"FAIL: {e}"
    try:
        async with async_session() as db:
            from sqlalchemy import select
            from app.models.user import User
            r = await db.execute(select(User).limit(5))
            users = r.scalars().all()
            results["users"] = str([{"id": u.id, "email": u.email, "role": u.role} for u in users])
    except Exception as e:
        results["users_query"] = f"FAIL: {traceback.format_exc()[-500:]}"
    try:
        from app.core.security import verify_password, hash_password
        results["security_import"] = "ok"
    except Exception as e:
        results["security_import"] = f"FAIL: {e}"
    try:
        from app.services import session_service
        results["session_import"] = "ok"
    except Exception as e:
        results["session_import"] = f"FAIL: {e}"
    return results


@app.get("/api/health", tags=["health"])
async def health_check():
    """Enhanced health check with dependency status."""
    checks: dict[str, str] = {"database": "unknown", "redis": "unknown"}

    # DB check
    try:
        async with async_session() as db:
            await db.execute(sqlalchemy.text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    # Redis check
    try:
        from app.core.redis_client import get_redis

        redis = await get_redis()
        if redis:
            await redis.ping()
            checks["redis"] = "ok"
        else:
            checks["redis"] = "unavailable"
    except Exception:
        checks["redis"] = "error"

    # Qdrant check
    if settings.FEATURE_RAG:
        try:
            from app.services.vector_store import _get_client

            client = _get_client()
            client.get_collections()
            checks["qdrant"] = "ok"
        except Exception:
            checks["qdrant"] = "error"

    # Embedding model check
    try:
        from app.services.vector_store import _embedding_model

        checks["embedding_model"] = "loaded" if _embedding_model is not None else "not_loaded"
    except Exception:
        checks["embedding_model"] = "unknown"

    # Event bus stats
    try:
        from app.core.event_bus import event_bus

        checks["event_bus"] = f"{event_bus.handler_count} handlers"
    except Exception:
        checks["event_bus"] = "unknown"

    is_healthy = checks["database"] == "ok"
    return {
        "status": "healthy" if is_healthy else "degraded",
        "checks": checks,
        "version": "2.0.0",
        "uptime_seconds": round(time.time() - _start_time),
    }
