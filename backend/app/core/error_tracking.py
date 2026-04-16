"""Sentry error tracking integration."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def init_sentry(dsn: str | None = None, env: str = "development") -> None:
    """Initialize Sentry SDK if DSN is provided."""
    if not dsn:
        logger.info("Sentry DSN not configured — error tracking disabled")
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=env,
            traces_sample_rate=0.1 if env == "production" else 1.0,
            profiles_sample_rate=0.1 if env == "production" else 0.0,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
            send_default_pii=False,
        )
        logger.info("Sentry initialized (env=%s)", env)
    except ImportError:
        logger.info("sentry-sdk not installed — error tracking disabled")
    except Exception as exc:
        logger.warning("Sentry init failed: %s", exc)
