"""Structured JSON logging with request ID tracking and sensitive data masking."""
from __future__ import annotations

import json
import logging
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[int | None] = ContextVar("user_id", default=None)

SENSITIVE_KEYS = {
    "password",
    "token",
    "secret",
    "api_key",
    "authorization",
    "hashed_password",
    "credit_card",
}


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON for structured log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(""),
        }
        uid = user_id_var.get(None)
        if uid:
            log_data["user_id"] = uid
        if record.exc_info and record.exc_info[0]:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data, ensure_ascii=False, default=str)


def mask_sensitive(data: dict) -> dict:
    """Recursively mask sensitive values in log data."""
    if not isinstance(data, dict):
        return data
    return {
        k: (
            "***MASKED***"
            if k.lower() in SENSITIVE_KEYS
            else mask_sensitive(v) if isinstance(v, dict) else v
        )
        for k, v in data.items()
    }


def setup_logging(env: str = "development") -> None:
    """Configure logging based on environment."""
    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler()
    if env == "production":
        handler.setFormatter(JSONFormatter())
        root.setLevel(logging.INFO)
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root.setLevel(logging.INFO)

    root.addHandler(handler)

    # Reduce noisy loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


_task_logger = logging.getLogger("app.tasks")


def log_task_execution(
    task_name: str,
    duration_ms: float,
    status: str,
    error: str | None = None,
) -> None:
    """Structured log for scheduler task execution."""
    _task_logger.info(
        "Task executed: %s [%s] in %.1fms%s",
        task_name,
        status,
        duration_ms,
        f" error={error}" if error else "",
        extra={"task_name": task_name, "duration_ms": duration_ms, "status": status},
    )
