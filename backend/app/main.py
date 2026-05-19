from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

import sqlalchemy

from app.api.v1.router import v1_router
from app.core.config import settings
from app.core.database import async_session, engine
from app.core.dependencies import require_role
from app.core.error_tracking import init_sentry
from app.core.logging_config import setup_logging, request_id_var
from app.core.metrics import PrometheusMiddleware, metrics_response
from app.models.enums import UserRole
from app.models.user import User
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.core.exceptions import AppException, app_exception_handler, unhandled_exception_handler
from app.core.middleware import (
    AuditLogMiddleware,
    CSRFProtectionMiddleware,
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

    # Production observability sanity check — log the Sentry-side
    # configuration once at boot so an operator scanning Render
    # logs immediately sees what's wired and what isn't.
    # Doesn't print secret values, only "configured/missing" booleans.
    if settings.ENV == "production":
        _obs_log = logging.getLogger(__name__)
        sentry_backend = bool(os.environ.get("SENTRY_DSN"))
        sentry_frontend = bool(os.environ.get("VITE_SENTRY_DSN"))
        sentry_release_token = bool(os.environ.get("SENTRY_AUTH_TOKEN"))
        sentry_tunnel = bool(os.environ.get("SENTRY_ALLOWED_PROJECT_IDS"))
        _obs_log.info(
            "observability: sentry_backend=%s sentry_frontend=%s "
            "sentry_release_token=%s sentry_tunnel_allowlist=%s",
            sentry_backend, sentry_frontend,
            sentry_release_token, sentry_tunnel,
        )
        if not sentry_backend:
            _obs_log.warning(
                "SENTRY_DSN not set — backend errors will not reach Sentry."
            )
        if not sentry_frontend:
            _obs_log.warning(
                "VITE_SENTRY_DSN not set on frontend service — "
                "frontend errors will not reach Sentry."
            )

    from app.core.database import Base

    _is_postgres = settings.DATABASE_URL.startswith("postgresql")

    # Regulated production: never mutate schema implicitly; use Alembic.
    if settings.is_development or settings.AUTO_CREATE_TABLES:
        # Create tables — checkfirst=True prevents UniqueViolationError on existing DBs
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created / verified")
        except Exception as e:
            # Tables may already exist with conflicting types — safe to continue
            logger.warning("create_all partial: %s", str(e)[:200])
    else:
        logger.info("AUTO_CREATE_TABLES disabled (env=%s)", settings.ENV)

    # Round-4 §3 schema-introspection sanity check. Mode is governed
    # by SCHEMA_DRIFT_MODE: ``off`` (default prod) skips entirely;
    # ``warn`` logs + Sentry breadcrumbs; ``fail`` raises and aborts
    # boot. Sync inspector → run on a thread so the lifespan's event
    # loop isn't blocked.
    try:
        from app.core.schema_check import run_schema_drift_check_on_startup
        from sqlalchemy import create_engine

        sync_url = settings.DATABASE_URL.replace("+asyncpg", "")
        sync_engine = create_engine(sync_url)

        def _run_check() -> None:
            try:
                run_schema_drift_check_on_startup(sync_engine, Base.metadata)
            finally:
                sync_engine.dispose()

        await asyncio.to_thread(_run_check)
    except Exception as exc:
        # Hook is opt-in — never break boot with a check failure.
        logger.warning("schema_check skipped: %s", exc)

    # PostgreSQL-only extensions and indexes (silent fail on SQLite)
    # Auto-sync schema: add missing columns to existing tables
    # This handles Render where tables were created by an older version.
    # Note: identifiers are interpolated into DDL via f-strings. The inputs
    # come from SQLAlchemy metadata (NOT user input), so injection is not a
    # direct threat, but we still validate every identifier against a strict
    # regex to prevent a future bug (e.g. a model name change injecting SQL)
    # from opening an injection window.
    import re as _re
    _IDENTIFIER_RE = _re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")

    def _safe_ident(name: str) -> str:
        if not _IDENTIFIER_RE.match(name):
            raise ValueError(f"Unsafe SQL identifier: {name!r}")
        return name

    if _is_postgres and (settings.is_development or settings.AUTO_SCHEMA_SYNC):
        try:
            async with engine.begin() as conn:
                for table in Base.metadata.sorted_tables:
                    table_name = _safe_ident(table.name)
                    for column in table.columns:
                        col_name = _safe_ident(column.name)
                        # col_type comes from SQLAlchemy dialect compiler — safe.
                        col_type = column.type.compile(engine.dialect)
                        default = ""
                        if column.default is not None and column.default.arg is not None:
                            dval = column.default.arg
                            if isinstance(dval, bool):
                                default = f" DEFAULT {'true' if dval else 'false'}"
                            elif isinstance(dval, (int, float)):
                                default = f" DEFAULT {dval}"
                            elif isinstance(dval, str):
                                # Escape single quotes in string defaults to block
                                # injection if a model ever carries a malicious default.
                                safe_dval = dval.replace("'", "''")
                                default = f" DEFAULT '{safe_dval}'"
                        sql = (
                            f"ALTER TABLE {table_name} "
                            f"ADD COLUMN IF NOT EXISTS {col_name} {col_type}{default}"
                        )
                        try:
                            await conn.execute(sqlalchemy.text(sql))
                        except Exception:
                            pass  # Column exists or type conflict — safe to skip
            logger.info("Schema auto-sync completed")
        except ValueError as ve:
            logger.error("Schema auto-sync aborted — unsafe identifier: %s", ve)
        except Exception as e:
            logger.warning("Schema auto-sync failed: %s", str(e)[:200])
    elif _is_postgres:
        logger.info("AUTO_SCHEMA_SYNC disabled (env=%s)", settings.ENV)

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
        # Score-change events (added in v1.7.0 EVT-1/EVT-2) — webhook
        # subscribers used to miss these because the bus subscription
        # list never grew. Audit EVT-5.
        event_bus.subscribe("lead.score_changed", _webhook_service.handle_event)
        event_bus.subscribe("opportunity.score_changed", _webhook_service.handle_event)
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

            # Required-field map per event_type (audit EVT-4). If a
            # publisher omits one of these keys the workflow handler
            # used to fail deep inside svc.evaluate_event with a
            # KeyError that got swallowed; now we log+skip so misuse
            # surfaces in logs without taking the dispatcher down.
            _WORKFLOW_REQUIRED_KEYS: dict[str, tuple[str, ...]] = {
                "opportunity.stage_changed": ("opportunity_id",),
                "quote.approved": ("quote_id",),
                "email.parsed": ("email_id",),
            }

            async def _on_workflow_event(event_type: str, payload: dict):
                event_map = {
                    "opportunity.stage_changed": ("opportunity", "stage_changed"),
                    "quote.approved": ("quote", "approved"),
                    "email.parsed": ("email", "parsed"),
                }
                required = _WORKFLOW_REQUIRED_KEYS.get(event_type, ())
                missing = [k for k in required if payload.get(k) is None]
                if missing:
                    logger.warning(
                        "Workflow event %s missing required keys %s — skipping",
                        event_type, missing,
                    )
                    return
                try:
                    async with async_session() as wf_db:
                        svc = WorkflowService(wf_db)
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

# ── Prometheus metrics ──
# Disable by setting ENABLE_METRICS=false in environments where metrics scraping isn't used.
if os.environ.get("ENABLE_METRICS", "true").lower() == "true":
    app.add_middleware(PrometheusMiddleware)


@app.get("/metrics")
async def metrics():
    return metrics_response()

# ── Rate limiter state ──
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ── Request ID + access log middleware ──
_access_logger = logging.getLogger("app.access")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a unique request ID to each request + emit structured access log.

    - Accepts inbound X-Request-ID (useful for tracing upstream proxies)
      or mints a fresh UUID.
    - Binds request_id as a Sentry tag so issues are searchable by it.
    - Emits one access log line per request with method/path/status/duration_ms
      so we can correlate latency + error rate without a full APM.
    """

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_var.set(rid)

        # Tag Sentry breadcrumbs/events so the issue UI can be filtered by
        # request_id and cross-referenced with backend logs.
        try:
            import sentry_sdk
            sentry_sdk.set_tag("request_id", rid)
        except ImportError:
            pass

        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            # Skip health probes — they'd 90% of the log volume.
            if request.url.path not in ("/api/health",):
                duration_ms = round((time.perf_counter() - start) * 1000, 1)
                _access_logger.info(
                    "access",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                    },
                )


# ── Middleware (order matters: last added = first executed) ──

# 0. Request ID tracking (outermost — runs first)
app.add_middleware(RequestIDMiddleware)

# 1. Security headers on all responses
app.add_middleware(SecurityHeadersMiddleware)

# 2. CSRF protection (cookie-authenticated requests only)
app.add_middleware(CSRFProtectionMiddleware)

# 3. Audit logging for state-changing requests
app.add_middleware(AuditLogMiddleware)

# 4. Request size limit
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

# Sentry tunnel — same-origin relay for browser events so ad blockers
# and corporate network filters can't drop frontend telemetry.
from app.api.sentry_tunnel import router as sentry_tunnel_router  # noqa: E402
app.include_router(sentry_tunnel_router, prefix="/api")


@app.post("/api/admin/seed-demo")
async def seed_demo_data(
    current_user: User = Depends(require_role(UserRole.SALES_MANAGER)),
):
    """One-time seed endpoint. Manager-only. Blocked in production."""
    import traceback

    if settings.is_production or not getattr(settings, "ENABLE_DEMO_SEED", False):
        raise HTTPException(
            status_code=404,
            detail="Not found",
        )

    results: dict[str, str] = {}

    try:
        return await _run_seed(results)
    except Exception as e:
        logger.exception("Seed failed for user %s", current_user.id)
        return {"status": "error", "error": "Seed failed", "results": results}


async def _run_seed(results: dict) -> dict:
    import json as _json
    from datetime import date, datetime, timedelta, timezone
    from sqlalchemy import select, func

    async with async_session() as db:
        from app.models.user import User
        from app.models.customer import Customer
        from app.models.spare_part import SparePart
        from app.models.price_entry import PriceEntry
        from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal
        from app.models.quote import Quote
        from app.models.quote_item import QuoteItem
        from app.models.lead import Lead
        from app.models.email_request import EmailRequest
        from app.core.security import hash_password

        # Guard: skip if data already exists
        opp_count = (await db.execute(select(func.count(Opportunity.id)))).scalar() or 0
        if opp_count > 3:
            return {"status": "skipped", "message": f"Data already exists ({opp_count} opportunities)"}

        NOW = datetime.now(timezone.utc)

        # ── Users (rep, ops) ──
        # Passwords come from env vars; fall back to random if not set.
        # IMPORTANT: Never log generated passwords.
        import secrets as _secrets
        generated_passwords: dict[str, str] = {}
        rep = (await db.execute(select(User).where(User.email == "rep@honeywell.com"))).scalar_one_or_none()
        if not rep:
            rep_pw = settings.DEMO_REP_PASSWORD or _secrets.token_urlsafe(18)
            rep = User(email="rep@honeywell.com", full_name="Elif Kaya", hashed_password=hash_password(rep_pw), role="sales_rep", is_active=True)
            db.add(rep)
            await db.flush()
            if not settings.DEMO_REP_PASSWORD:
                generated_passwords["rep@honeywell.com"] = rep_pw
            results["rep"] = f"created id={rep.id}"
        ops = (await db.execute(select(User).where(User.email == "ops@honeywell.com"))).scalar_one_or_none()
        if not ops:
            ops_pw = settings.DEMO_OPS_PASSWORD or _secrets.token_urlsafe(18)
            ops = User(email="ops@honeywell.com", full_name="Mehmet Demir", hashed_password=hash_password(ops_pw), role="operations", is_active=True)
            db.add(ops)
            await db.flush()
            if not settings.DEMO_OPS_PASSWORD:
                generated_passwords["ops@honeywell.com"] = ops_pw
            results["ops"] = f"created id={ops.id}"
        admin = (await db.execute(select(User).where(User.email == "admin@honeywell.com"))).scalar_one_or_none()

        # ── Customers (10) ──
        cust_count = (await db.execute(select(func.count(Customer.id)))).scalar() or 0
        customers = []
        if cust_count < 5:
            cust_data = [
                ("Anadolu Endustri A.S.", "Anadolu", "satis@anadoluendustri.com.tr", "+90 212 555 0101"),
                ("Ege Mekatronik Ltd.", "Ege Mekatronik", "info@egemekatronik.com", "+90 232 555 0202"),
                ("Karadeniz Otomasyon", "Karadeniz Oto", "siparis@karadenizoto.com.tr", "+90 462 555 0303"),
                ("Ankara Teknik Servis", "Ankara Teknik", "destek@ankarateknik.com.tr", "+90 312 555 0404"),
                ("Marmara HVAC Systems", "Marmara HVAC", "purchasing@marmarahvac.com", "+90 216 555 0505"),
                ("Akdeniz Proses", "Akdeniz Proses", "tedarik@akdenizproses.com.tr", "+90 242 555 0606"),
                ("Trakya Endustriyel", "Trakya End.", "satis@trakyaend.com.tr", "+90 284 555 0707"),
                ("GAP Muhendislik", "GAP Muh.", "proje@gapmuh.com.tr", "+90 414 555 0808"),
                ("Bolu Termal Sistemler", "Bolu Termal", "info@bolutermal.com", "+90 374 555 0909"),
                ("Kocaeli Filtre San.", "Kocaeli Filtre", "siparis@kocaelifiltre.com.tr", "+90 262 555 1010"),
            ]
            for name, company, email, phone in cust_data:
                c = Customer(name=name, company=company, email=email, phone=phone)
                db.add(c)
                customers.append(c)
            await db.flush()
            results["customers"] = f"created {len(customers)}"

        all_customers = (await db.execute(select(Customer).order_by(Customer.id))).scalars().all()

        # ── Spare Parts (10) ──
        part_count = (await db.execute(select(func.count(SparePart.id)))).scalar() or 0
        if part_count < 5:
            parts_data = [
                ("HW-VALVE-001", "Pnomatik Aktuator", "Pneumatic Actuator", "valve"),
                ("HW-ACTU-002", "Elektrik Aktuator 24V", "Electric Actuator 24V", "actuator"),
                ("HW-CTRL-001", "PLC Kontrolor HC900", "PLC Controller HC900", "controller"),
                ("HW-CTRL-002", "DCS Modul C300", "DCS Module C300", "controller"),
                ("HW-SENS-001", "Sicaklik Sensoru PT100", "Temperature Sensor PT100", "sensor"),
                ("HW-SENS-002", "Basinc Transmiteri", "Pressure Transmitter", "sensor"),
                ("HW-FLTR-001", "Hava Filtresi Panel 20x20", "Air Filter Panel 20x20", "filter"),
                ("HW-FLTR-002", "HEPA Filtre H13", "HEPA Filter H13", "filter"),
                ("HW-ANAL-001", "Gaz Analizoru", "Gas Analyzer", "analyzer"),
                ("HW-FLOW-001", "Debi Olcer Versaflow", "Flow Meter Versaflow", "flow"),
            ]
            for code, name_tr, name_en, cat in parts_data:
                p = SparePart(honeywell_code=code, name_tr=name_tr, name_en=name_en, category=cat)
                db.add(p)
            await db.flush()
            results["parts"] = f"created {len(parts_data)}"

        all_parts = (await db.execute(select(SparePart).order_by(SparePart.id))).scalars().all()

        # ── Opportunities (8) ──
        if opp_count < 3:
            opp_data = [
                ("Anadolu Endustri - HVAC Yenileme", "proposal", 125000, "TRY"),
                ("Ege Mekatronik - PLC Upgrade", "negotiation", 270000, "TRY"),
                ("Karadeniz - Sensor Paketi", "qualified", 85000, "TRY"),
                ("Marmara HVAC - Yillik Bakim", "prospecting", 50000, "TRY"),
                ("GAP Muhendislik - DCS Modernizasyon", "proposal", 450000, "USD"),
                ("Bolu Termal - Filtre Tedarikat", "negotiation", 35000, "TRY"),
                ("Kocaeli Filtre - Yillik Tedarikat", "qualified", 120000, "TRY"),
                ("Akdeniz Proses - Otomasyon Paketi", "negotiation", 310000, "TRY"),
            ]
            for i, (title, stage, amount, currency) in enumerate(opp_data):
                cust = all_customers[i % len(all_customers)] if all_customers else None
                o = Opportunity(
                    title=title, stage=stage, amount=amount, currency=currency,
                    customer_id=cust.id if cust else None,
                    owner_id=admin.id if admin else (rep.id if rep else 1),
                    close_date=date.today() + timedelta(days=30 + i * 15),
                )
                db.add(o)
            await db.flush()
            results["opportunities"] = f"created {len(opp_data)}"

        # ── Pipeline Snapshots (4 weeks) ──
        from app.models.forecast import PipelineSnapshot
        snap_count = (await db.execute(select(func.count(PipelineSnapshot.id)))).scalar() or 0
        if snap_count == 0:
            stages = [("prospecting", 5, 150000), ("qualified", 4, 280000), ("proposal", 6, 420000), ("negotiation", 3, 350000)]
            for week in range(4):
                snap_date = (NOW - timedelta(weeks=3 - week)).date()
                growth = 1 + week * 0.12
                for stage, count, total in stages:
                    db.add(PipelineSnapshot(snapshot_date=snap_date, stage=stage, opportunity_count=int(count * growth), total_amount=round(total * growth, 2), weighted_amount=round(total * growth * 0.6, 2)))
            await db.flush()
            results["snapshots"] = "created 16"

        # ── Competitor Mentions ──
        from app.models.competitor_mention import CompetitorMention
        cm_count = (await db.execute(select(func.count(CompetitorMention.id)))).scalar() or 0
        if cm_count == 0:
            for comp, sent, snippet, days in [
                ("Siemens", "negative", "Siemens PLC fiyatlari ile karsilastirma", 2),
                ("Siemens", "positive", "Siemens teslimat 8 hafta, biz 4 hafta", 8),
                ("ABB", "negative", "ABB yeni seri degerlendiriliyor", 5),
                ("ABB", "positive", "ABB ile ayni kalite, fiyat avantajimiz var", 12),
                ("Schneider", "positive", "Schneider otomasyon daha pahali", 15),
                ("Emerson", "positive", "Emerson DCS gecis planlaniyor", 7),
                ("Yokogawa", "positive", "Yokogawa teklif vermis ama servis agimiz genis", 20),
            ]:
                db.add(CompetitorMention(competitor_name=comp, source_entity_type="email", source_entity_id=1, context_snippet=snippet, sentiment=sent, detected_by="keyword", created_at=NOW - timedelta(days=days)))
            await db.flush()
            results["competitors"] = "created 7"

        # ── Pipelines ──
        from app.models.pipeline import Pipeline
        pipe_count = (await db.execute(select(func.count(Pipeline.id)))).scalar() or 0
        if pipe_count == 0:
            for name, desc, is_default, stages_json in [
                ("Standart Satis", "Standart satis pipeline", True, _json.dumps([{"key":"prospecting","label":"Arastirma","order":1,"probability":10},{"key":"qualified","label":"Nitelenmis","order":2,"probability":25},{"key":"proposal","label":"Teklif","order":3,"probability":50},{"key":"negotiation","label":"Muzakere","order":4,"probability":75},{"key":"closed_won","label":"Kazanildi","order":5,"probability":100},{"key":"closed_lost","label":"Kaybedildi","order":6,"probability":0}])),
                ("Hizli Satis", "Hizli satis pipeline", False, _json.dumps([{"key":"qualified","label":"Nitelenmis","order":1,"probability":30},{"key":"proposal","label":"Teklif","order":2,"probability":60},{"key":"closed_won","label":"Kazanildi","order":3,"probability":100},{"key":"closed_lost","label":"Kaybedildi","order":4,"probability":0}])),
            ]:
                db.add(Pipeline(name=name, description=desc, is_default=is_default, stages_json=stages_json, created_by=admin.id if admin else 1))
            await db.flush()
            results["pipelines"] = "created 2"

        # ── Territories ──
        from app.models.territory import Territory
        terr_count = (await db.execute(select(func.count(Territory.id)))).scalar() or 0
        if terr_count == 0:
            t1 = Territory(name="Marmara Bolgesi", description="Istanbul, Bursa, Kocaeli", region="Marmara", created_by=admin.id if admin else 1, tenant_id=admin.tenant_id if admin else 1)
            t2 = Territory(name="Ege-Akdeniz Bolgesi", description="Izmir, Antalya, Mugla", region="Ege", created_by=admin.id if admin else 1, tenant_id=admin.tenant_id if admin else 1)
            t3 = Territory(name="Ic Anadolu", description="Ankara, Konya, Eskisehir", region="Ic Anadolu", created_by=admin.id if admin else 1, tenant_id=admin.tenant_id if admin else 1)
            db.add_all([t1, t2, t3])
            await db.flush()
            results["territories"] = "created 3"

        # ── Report Templates ──
        from app.models.report import ReportTemplate
        rt_count = (await db.execute(select(func.count(ReportTemplate.id)))).scalar() or 0
        if rt_count == 0:
            templates = [
                ("Aylik Satis Raporu", "opportunity", '["title","stage","amount","close_date"]', "bar", "stage"),
                ("Teklif Durum Ozeti", "quote", '["quote_number","status","grand_total","created_at"]', "pie", "status"),
                ("Musteri Listesi", "customer", '["name","company","email","phone"]', "table", None),
            ]
            for name, etype, cols, chart, group in templates:
                db.add(ReportTemplate(name=name, entity_type=etype, columns_json=cols, chart_type=chart, group_by=group, sort_by=group or "created_at", sort_order="desc", created_by=admin.id if admin else 1))
            await db.flush()
            results["report_templates"] = "created 3"

        # ── Contracts ──
        from app.models.contract import Contract
        ct_count = (await db.execute(select(func.count(Contract.id)))).scalar() or 0
        # Round-15 — every seeded row needs ``tenant_id`` since most parent
        # tables flipped to NOT NULL via cohort 1-6 promotions. Cache the
        # admin's tenant locally so each ctor below stays compact.
        _seed_tenant_id = admin.tenant_id if admin else 1

        if ct_count == 0 and all_customers:
            for title, cust_idx, val in [("Anadolu HVAC Bakim", 0, 250000), ("Ege Sensor Tedarikat", 1, 180000)]:
                db.add(Contract(title=title, customer_id=all_customers[cust_idx].id if len(all_customers) > cust_idx else 1, value=val, status="active", start_date=date.today() - timedelta(days=90), end_date=date.today() + timedelta(days=275), created_by=admin.id if admin else 1, tenant_id=_seed_tenant_id))
            await db.flush()
            results["contracts"] = "created 2"

        # ── Workflow Rules ──
        from app.models.workflow_rule import WorkflowRule
        wf_count = (await db.execute(select(func.count(WorkflowRule.id)))).scalar() or 0
        if wf_count == 0:
            db.add(WorkflowRule(name="Yuksek Deger Firsat Bildirimi", entity_type="opportunity", trigger_event="stage_change", conditions_json='{"conditions":[{"field":"amount","operator":"gt","value":100000}]}', actions_json='{"actions":[{"type":"notification","target":"manager"}]}', flow_json='{"nodes":[],"edges":[]}', is_active=True, created_by=admin.id if admin else 1, tenant_id=_seed_tenant_id))
            await db.flush()
            results["workflow_rules"] = "created 1"

        await db.commit()

    if generated_passwords:
        return {"status": "ok", "results": results, "generated_passwords": generated_passwords}
    return {"status": "ok", "results": results}


@app.api_route("/", methods=["GET", "HEAD"], tags=["health"], include_in_schema=False)
async def root():
    """Cheap liveness probe at the domain root.

    UptimeRobot's free tier defaults to monitoring the root URL of the
    monitored host. Returning 200 here gives a second up/down signal
    independent of /api/health (which can flip to ``degraded`` when a
    breaker is open). Intentionally minimal — no DB, no I/O.
    """
    return {"service": "honeywell-sales-suite", "status": "ok"}


@app.api_route("/api/health", methods=["GET", "HEAD"], tags=["health"])
async def health_check():
    """Enhanced health check with dependency status."""
    checks: dict[str, str] = {"database": "unknown"}

    # DB check
    try:
        async with async_session() as db:
            await db.execute(sqlalchemy.text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    # Redis intentionally not probed — the project no longer uses Redis.
    # ``app/core/redis_client.py`` is a no-op stub; reporting "redis" in
    # this payload would just confuse operators looking for a dependency
    # we don't actually have. See the stub's docstring for the rationale.

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

    # Circuit breaker states — operational visibility for external API health
    circuits: dict[str, dict[str, str | int]] = {}
    try:
        from app.core.circuit_breaker import (
            claude_breaker,
            currency_breaker,
            graph_breaker,
            qdrant_breaker,
        )

        for breaker in (claude_breaker, graph_breaker, currency_breaker, qdrant_breaker):
            circuits[breaker.name] = {
                "state": breaker.state,
                "failure_count": breaker._failure_count,
            }
    except Exception:
        circuits = {"error": "unavailable"}

    is_healthy = checks["database"] == "ok"
    any_breaker_open = any(
        isinstance(c, dict) and c.get("state") == "open" for c in circuits.values()
    )
    if any_breaker_open and is_healthy:
        status = "degraded"
    else:
        status = "healthy" if is_healthy else "degraded"

    return {
        "status": status,
        "checks": checks,
        "circuits": circuits,
        "version": "2.0.0",
        "uptime_seconds": round(time.time() - _start_time),
    }


@app.get("/api/debug/sentry-test", tags=["debug"])
async def sentry_test(token: str = ""):
    """One-shot hook for verifying Sentry event delivery.

    Guarded by a token so it can't be abused as a cheap way to spike the
    error quota. Expected to be removed once Sentry is confirmed working.
    """
    if not settings.SENTRY_DSN or token != settings.SENTRY_TEST_TOKEN:
        raise HTTPException(status_code=404, detail="Not found")
    raise RuntimeError("sentry-test — intentional error to verify delivery")
