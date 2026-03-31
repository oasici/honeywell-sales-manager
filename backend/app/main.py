from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import sqlalchemy

from app.api.v1.router import v1_router
from app.core.config import settings
from app.core.database import async_session, engine
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

scheduler = AsyncIOScheduler()

# ── Rate limiter ──
limiter = Limiter(key_func=get_remote_address, default_limits=[settings.RATE_LIMIT_API])


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Async lifespan: startup and shutdown logic."""
    from app.core.database import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created / verified")

    # Auto-migrate: add missing columns safely
    try:
        async with engine.begin() as conn:
            migrations = [
                "ALTER TABLE spare_parts ADD COLUMN IF NOT EXISTS info TEXT",
                "ALTER TABLE spare_parts ADD COLUMN IF NOT EXISTS model_number VARCHAR(200)",
                "ALTER TABLE spare_parts ADD COLUMN IF NOT EXISTS transfer_price FLOAT",
                "ALTER TABLE spare_parts ADD COLUMN IF NOT EXISTS supplier_price FLOAT",
                "ALTER TABLE spare_parts ADD COLUMN IF NOT EXISTS price_currency VARCHAR(10)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_change_required BOOLEAN DEFAULT false",
                "ALTER TABLE email_requests ADD COLUMN IF NOT EXISTS is_read BOOLEAN DEFAULT false",
                "ALTER TABLE email_requests ADD COLUMN IF NOT EXISTS last_parsed_at TIMESTAMP WITH TIME ZONE",
            ]
            for sql in migrations:
                await conn.execute(sqlalchemy.text(sql))
        logger.info("Auto-migration completed")
    except Exception as e:
        logger.warning("Auto-migration failed (may already be applied): %s", e)

    for dir_path in [settings.QUOTES_DIR, settings.UPLOADS_DIR]:
        os.makedirs(dir_path, exist_ok=True)

    from app.services.auth_service import create_default_admin
    async with async_session() as db:
        await create_default_admin(db)

    scheduler.start()
    logger.info("Application started (env=%s)", settings.ENV)

    yield

    scheduler.shutdown(wait=False)
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
