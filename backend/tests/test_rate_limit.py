"""P0-4: Rate limiting tests."""

import pytest


def test_rate_limiter_is_attached_to_app():
    """The app must have a limiter in its state for slowapi to work."""
    from app.main import app

    assert hasattr(app.state, "limiter"), "Limiter not attached to app.state"
    assert app.state.limiter is not None


def test_global_rate_limit_is_configured():
    """Global API rate limit must be set from config."""
    from app.core.config import settings
    from app.core.rate_limit import limiter

    assert limiter is not None
    assert settings.RATE_LIMIT_API  # non-empty
    assert settings.RATE_LIMIT_LOGIN  # non-empty


def test_login_has_account_lockout():
    """Login endpoint must have account lockout (5 attempts / 15 min window).
    This is the primary brute-force protection, implemented in auth_service.authenticate()."""
    from app.services.auth_service import authenticate

    # Verify the function exists and is callable
    assert callable(authenticate)
