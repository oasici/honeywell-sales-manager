from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

import sqlalchemy

from app.api.v1.router import v1_router
from app.core.config import settings
from app.core.database import async_session, engine
from app.tasks.scheduler import start_scheduler, stop_scheduler
from app.core.exceptions import AppException, app_exception_handler, unhandled_exception_handler
from app.core.middleware import (
    AuditLogMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.models import *  # noqa: F401, F403

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Rate limiter (shared instance) ──
from app.core.rate_limit import limiter


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Async lifespan: startup and shutdown logic."""
    from app.core.database import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created / verified")

    # Auto-migrate: additive-only DDL (no destructive UPDATE/DELETE)
    # NOTE: Destructive one-time cleanups have been removed.
    # For new schema changes, use Alembic: alembic revision --autogenerate
    _additive_migrations = [
        "ALTER TABLE spare_parts ADD COLUMN IF NOT EXISTS info TEXT",
        "ALTER TABLE spare_parts ADD COLUMN IF NOT EXISTS model_number VARCHAR(200)",
        "ALTER TABLE spare_parts ADD COLUMN IF NOT EXISTS transfer_price FLOAT",
        "ALTER TABLE spare_parts ADD COLUMN IF NOT EXISTS supplier_price FLOAT",
        "ALTER TABLE spare_parts ADD COLUMN IF NOT EXISTS price_currency VARCHAR(10)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_change_required BOOLEAN DEFAULT false",
        "ALTER TABLE email_requests ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT false",
        "ALTER TABLE email_requests ADD COLUMN IF NOT EXISTS last_parsed_at TIMESTAMP WITH TIME ZONE",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_quote_email_request ON quotes (email_request_id) WHERE email_request_id IS NOT NULL",
        "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS close_reason VARCHAR(50)",
        "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP WITH TIME ZONE",
        "ALTER TABLE quotes ADD COLUMN IF NOT EXISTS opportunity_id INTEGER REFERENCES opportunities(id)",
        "CREATE INDEX IF NOT EXISTS ix_quotes_opportunity_id ON quotes (opportunity_id)",
    ]
    for sql in _additive_migrations:
        try:
            async with engine.begin() as conn:
                await conn.execute(sqlalchemy.text(sql))
        except Exception as e:
            logger.debug("Migration skipped (already applied or N/A): %s", str(e)[:100])
    logger.info("Auto-migration completed (additive only)")

    # Fail-fast: production requires ENCRYPTION_KEY
    if settings.is_production and not os.environ.get("ENCRYPTION_KEY"):
        raise RuntimeError(
            "ENCRYPTION_KEY environment variable is required in production. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )

    for dir_path in [settings.QUOTES_DIR, settings.UPLOADS_DIR]:
        os.makedirs(dir_path, exist_ok=True)

    from app.services.auth_service import create_default_admin
    async with async_session() as db:
        await create_default_admin(db)

    # Scheduler: only start if SCHEDULER_ENABLED=true (separate process in production)
    scheduler_enabled = os.environ.get("SCHEDULER_ENABLED", "true").lower() == "true"
    if scheduler_enabled:
        start_scheduler()
        logger.info("Scheduler started (in-process mode)")
    else:
        logger.info("Scheduler disabled (using separate scheduler process)")

    # Start audit buffer flush task
    from app.core.audit_buffer import start_audit_buffer, stop_audit_buffer
    start_audit_buffer()

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

# ── Middleware (order matters: last added = first executed) ──

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


@app.get("/api/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "service": "honeywell-sales-manager"}
