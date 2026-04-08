"""Application configuration via environment variables."""

import secrets

from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Environment ──
    ENV: str = "development"  # development | staging | production

    # ── Database ──
    DATABASE_URL: str = ""

    # ── Auth / JWT ──
    JWT_SECRET_KEY: str = secrets.token_hex(32)  # Random per-start in dev; MUST set in .env for prod
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Default Admin ──
    DEFAULT_ADMIN_EMAIL: str = "admin@honeywell.com"
    DEFAULT_ADMIN_PASSWORD: str = ""

    @model_validator(mode="after")
    def _validate_production_settings(self):
        import logging as _log
        if self.ENV == "production":
            if not self.DATABASE_URL:
                raise ValueError("DATABASE_URL must be set in production environment")
            if len(self.JWT_SECRET_KEY) < 32:
                _log.getLogger(__name__).warning(
                    "JWT_SECRET_KEY should be at least 32 characters in production"
                )
            origins = [o.strip().lower() for o in self.CORS_ORIGINS.split(",") if o.strip()]
            if any("localhost" in o or "127.0.0.1" in o for o in origins):
                raise ValueError(
                    "CORS_ORIGINS uretim ortaminda 'localhost' veya '127.0.0.1' icermemeli"
                )
        return self

    # ── CORS ──
    CORS_ORIGINS: str = "http://localhost,http://localhost:80,http://localhost:5173"

    # ── Microsoft Graph API ──
    AZURE_TENANT_ID: str = ""
    AZURE_CLIENT_ID: str = ""
    AZURE_CLIENT_SECRET: str = ""
    GRAPH_USER_EMAIL: str = ""
    GRAPH_WEBHOOK_SECRET: str = ""

    # ── Internal email domains (skip parsing) ──
    INTERNAL_EMAIL_DOMAINS: str = "honeywell.com,honeywell.com.tr"

    # ── SMTP ──
    SMTP_HOST: str = "smtp.office365.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_ADDRESS: str = ""

    # ── AI / LLM ──
    ANTHROPIC_API_KEY: str = ""
    AI_MODEL_NAME: str = "claude-sonnet-4-20250514"
    AI_MAX_TOKENS: int = 1024
    AI_TEMPERATURE: float = 1.0
    AI_MAX_RETRIES: int = 3
    AI_TIMEOUT_SECONDS: int = 30
    AI_FALLBACK_STRATEGY: str = "claude-first"  # claude-first | regex-first

    # ── Company ──
    COMPANY_NAME: str = "Honeywell Turkey"
    COMPANY_ADDRESS: str = "Istanbul, Turkey"
    COMPANY_PHONE: str = "+90 212 000 0000"
    COMPANY_TAX_ID: str = ""

    # ── Quote ──
    QUOTE_PREFIX: str = "HW-2026-"
    DEFAULT_TAX_RATE: float = 20.0
    DEFAULT_CURRENCY: str = "TRY"
    QUOTE_VALIDITY_DAYS: int = 30

    # ── Paths ──
    QUOTES_DIR: str = "data/quotes"
    UPLOADS_DIR: str = "data/uploads"
    TEMPLATES_DIR: str = "app/templates"

    # ── Scheduling ──
    EMAIL_POLL_INTERVAL_MINUTES: int = 5

    # ── Rate Limiting ──
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_API: str = "100/minute"

    # ── Security ──
    ALLOWED_UPLOAD_EXTENSIONS: str = ".csv,.xlsx,.xls"
    MAX_UPLOAD_SIZE_MB: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def internal_domains_list(self) -> list[str]:
        return [d.strip().lower() for d in self.INTERNAL_EMAIL_DOMAINS.split(",") if d.strip()]

    @property
    def allowed_extensions(self) -> set[str]:
        return {e.strip().lower() for e in self.ALLOWED_UPLOAD_EXTENSIONS.split(",") if e.strip()}

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
