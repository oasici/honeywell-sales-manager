"""A8: Production configuration validation tests."""

import pytest


def test_cors_localhost_rejected_in_production():
    """Production mode must reject CORS origins containing localhost."""
    from app.core.config import Settings

    with pytest.raises(ValueError, match="localhost"):
        Settings(
            ENV="production",
            DATABASE_URL="postgresql+asyncpg://x:x@db/test",
            JWT_SECRET_KEY="a" * 64,
            CORS_ORIGINS="http://localhost:5173,https://my-app.onrender.com",
        )


def test_cors_127_rejected_in_production():
    """Production mode must reject CORS origins containing 127.0.0.1."""
    from app.core.config import Settings

    with pytest.raises(ValueError, match="127.0.0.1"):
        Settings(
            ENV="production",
            DATABASE_URL="postgresql+asyncpg://x:x@db/test",
            JWT_SECRET_KEY="a" * 64,
            CORS_ORIGINS="http://127.0.0.1:3000",
        )


def test_cors_valid_origins_pass_in_production():
    """Production mode should accept valid non-localhost origins."""
    from app.core.config import Settings

    s = Settings(
        ENV="production",
        DATABASE_URL="postgresql+asyncpg://x:x@db/test",
        JWT_SECRET_KEY="a" * 64,
        CORS_ORIGINS="https://my-app.onrender.com,https://honeywell.com",
    )
    assert s.ENV == "production"


def test_cors_localhost_allowed_in_development():
    """Development mode should allow localhost in CORS."""
    from app.core.config import Settings

    s = Settings(
        ENV="development",
        CORS_ORIGINS="http://localhost:5173",
    )
    assert "localhost" in s.CORS_ORIGINS
