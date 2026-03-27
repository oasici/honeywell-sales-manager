"""Application configuration via environment variables."""

import secrets

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # ── Environment ──
    ENV: str = "development"  # development | staging | production

    # ── Database ──
    DATABASE_URL: str = "postgresql+asyncpg://honeywell:honeywell123@db:5432/honeywell_sales"

    # ── Auth / JWT ──
    JWT_SECRET_KEY: str = secrets.token_hex(32)  # Random per-start in dev; MUST set in .env for prod
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Default Admin ──
    DEFAULT_ADMIN_EMAIL: str = "admin@honeywell.com"
    DEFAULT_ADMIN_PASSWORD: str = "Admin123!"

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

    # ── Anthropic ──
    ANTHROPIC_API_KEY: str = ""

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
