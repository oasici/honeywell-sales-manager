"""Security and audit middleware."""

import json
import logging
import time
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        return response


class AuditLogMiddleware(BaseHTTPMiddleware):
    """Log all state-changing API requests for audit trail."""

    AUDITED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    async def dispatch(self, request: Request, call_next):
        if request.method not in self.AUDITED_METHODS:
            return await call_next(request)

        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # Skip login endpoint to avoid logging credentials
        if "/auth/login" in request.url.path:
            response = await call_next(request)
            if response.status_code == 200:
                logger.info(
                    "AUDIT: LOGIN success from %s",
                    request.client.host if request.client else "unknown",
                )
            else:
                logger.warning(
                    "AUDIT: LOGIN failed from %s",
                    request.client.host if request.client else "unknown",
                )
            return response

        start = time.time()
        response = await call_next(request)
        duration = round((time.time() - start) * 1000, 1)

        # Extract user info from auth header
        user_id = "anonymous"
        auth = request.headers.get("authorization", "")
        if auth.startswith("Bearer "):
            from app.core.security import decode_token
            payload = decode_token(auth[7:])
            if payload:
                user_id = payload.get("sub", "unknown")

        ip = request.client.host if request.client else "unknown"

        # Buffer audit entry (no DB write per request)
        from app.core.audit_buffer import enqueue_audit
        enqueue_audit(
            user_id=str(user_id),
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration,
            ip_address=ip,
        )

        logger.info(
            "AUDIT: user=%s method=%s path=%s status=%d duration=%sms ip=%s",
            user_id, request.method, request.url.path,
            response.status_code, duration, ip,
        )

        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests larger than MAX_UPLOAD_SIZE_MB."""

    def __init__(self, app, max_size_mb: int = 10):
        super().__init__(app)
        self.max_size = max_size_mb * 1024 * 1024

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > self.max_size:
            return Response(
                content=json.dumps({"error": {"code": "PAYLOAD_TOO_LARGE", "message": "Dosya boyutu cok buyuk"}}),
                status_code=413,
                media_type="application/json",
            )
        return await call_next(request)
