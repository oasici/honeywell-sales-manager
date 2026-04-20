"""Security and audit middleware."""

import json
import logging
import time
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_csp() -> str:
    """Build Content-Security-Policy from configured CORS origins.

    Allows connect-src to hit the configured frontend/backend origins so that
    the SPA can reach the API when deployed on a different subdomain (e.g.
    Render where frontend is on onrender.com and backend is on another host).
    """
    # Extra origins from CORS config for connect-src
    extra_origins = " ".join(o for o in settings.cors_origin_list if o.startswith("http"))
    connect_src = f"connect-src 'self' {extra_origins}".strip()

    return (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "img-src 'self' data: blob:; "
        "font-src 'self' https://fonts.gstatic.com; "
        f"{connect_src}; "
        "object-src 'none'; "
        "base-uri 'self'; "
        "form-action 'self'; "
        "frame-ancestors 'none'"
    )


# Build once at import — CSP doesn't change per-request
_CSP_VALUE = _build_csp()


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
        response.headers["Content-Security-Policy"] = _CSP_VALUE
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


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """Enforce CSRF protection on cookie-authenticated state-changing requests.

    Design (double-submit cookie):
    - `csrf_token` cookie is set by /auth/login (NOT HttpOnly — JS can read)
    - Frontend echoes the cookie value in `X-CSRF-Token` header on unsafe requests
    - Middleware compares the two; mismatch → 403

    Only enforced when the request uses cookie auth AND is state-changing.
    Authorization-header-based clients (CLI/tests) bypass the check since they
    are not vulnerable to CSRF (no ambient credential sent by the browser).
    """

    UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

    # Paths that must never enforce CSRF (pre-auth endpoints)
    EXEMPT_PATHS = (
        "/api/v1/auth/login",
        "/api/v1/auth/refresh",
        "/api/v1/auth/logout",
    )

    async def dispatch(self, request: Request, call_next):
        if request.method not in self.UNSAFE_METHODS:
            return await call_next(request)

        # Only enforce for API routes
        if not request.url.path.startswith("/api/"):
            return await call_next(request)

        # Skip exempt paths
        for exempt in self.EXEMPT_PATHS:
            if request.url.path.startswith(exempt):
                return await call_next(request)

        # If the client presents an Authorization header, it's not using
        # ambient cookie auth — CSRF does not apply.
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            return await call_next(request)

        # Otherwise, the request is relying on the cookie. Verify CSRF.
        cookie_token = request.cookies.get("csrf_token")
        header_token = request.headers.get("x-csrf-token")

        # If no cookie at all, the user isn't authenticated — let endpoint's
        # normal auth check return 401 (don't double up with 403).
        if not cookie_token:
            return await call_next(request)

        from app.core.security import verify_csrf_token
        if not verify_csrf_token(header_token or "", cookie_token):
            logger.warning(
                "CSRF rejected: method=%s path=%s ip=%s",
                request.method,
                request.url.path,
                request.client.host if request.client else "?",
            )
            return Response(
                content=json.dumps({
                    "error": {
                        "code": "CSRF_INVALID",
                        "message": "CSRF token gecersiz veya eksik.",
                    }
                }),
                status_code=403,
                media_type="application/json",
            )

        return await call_next(request)


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
