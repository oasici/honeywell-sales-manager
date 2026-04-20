"""Custom exception hierarchy with production-safe error responses."""

import logging
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(self, status_code: int, detail: str, error_code: str = "ERROR"):
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code


class NotFoundException(AppException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=404, detail=detail, error_code="NOT_FOUND")


class ForbiddenException(AppException):
    def __init__(self, detail: str = "Access denied"):
        super().__init__(status_code=403, detail=detail, error_code="FORBIDDEN")


class BadRequestException(AppException):
    def __init__(self, detail: str = "Bad request"):
        super().__init__(status_code=400, detail=detail, error_code="BAD_REQUEST")


class UnauthorizedException(AppException):
    def __init__(self, detail: str = "Not authenticated"):
        super().__init__(status_code=401, detail=detail, error_code="UNAUTHORIZED")


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle known application exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.error_code,
                "message": exc.detail,
            }
        },
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions. Never leak internals in production."""
    logger.error(
        "Unhandled exception: %s %s - %s\n%s",
        request.method,
        request.url.path,
        str(exc),
        traceback.format_exc(),
    )

    # Only leak exception details in local development. Staging/sandbox are
    # internet-facing and must mask internals to avoid path/implementation leak.
    detail = str(exc) if settings.is_development else "Beklenmeyen bir hata olustu"

    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": detail,
            }
        },
    )
