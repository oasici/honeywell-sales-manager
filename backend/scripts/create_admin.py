"""Create (or upsert) a single admin user — safe for production use.

The app's "admin" is the ``operations`` role (Admin → Users / Field
Permissions / Integrations / Audit / DLQ are operations-only). This
script provisions one such account without seeding any demo data, so it
is safe to run against a live database (e.g. on Render).

Design choices for production safety:
  * Credentials come from the ENVIRONMENT, never argv — so the password
    never lands in shell history, process listings, or CI logs.
  * If ``ADMIN_PASSWORD`` is omitted, a strong random one is generated,
    printed once, and ``password_change_required=True`` is set so the
    operator must rotate it on first login.
  * Idempotent: re-running with the same ``ADMIN_EMAIL`` updates the
    existing row (role/name/active) instead of erroring — but it will
    NOT silently reset the password unless ``ADMIN_PASSWORD`` is given
    or ``ADMIN_RESET_PASSWORD=1`` is set, so a re-run can't lock out a
    working admin by accident.
  * ``tenant_id`` defaults to NULL → the platform's default tenant
    (matches the existing ``admin@honeywell.com`` account). Override
    with ``ADMIN_TENANT_ID`` for a specific tenant.

Usage (on Render — DATABASE_URL is already in the service env):
    ADMIN_EMAIL='ops@firma.com' ADMIN_NAME='Ad Soyad' \
        PYTHONPATH=. python -m scripts.create_admin

    # supply your own password instead of an auto-generated one:
    ADMIN_EMAIL='ops@firma.com' ADMIN_NAME='Ad Soyad' \
        ADMIN_PASSWORD='S3cret!Pass' PYTHONPATH=. python -m scripts.create_admin

    # force a password reset on an existing account:
    ADMIN_EMAIL='ops@firma.com' ADMIN_RESET_PASSWORD=1 \
        PYTHONPATH=. python -m scripts.create_admin
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import string
import sys
from pathlib import Path

# Add backend to path so ``app.*`` imports resolve from the script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
logger = logging.getLogger("create_admin")

_ALLOWED_ROLES = {"operations", "sales_manager", "sales_rep"}
_PASSWORD_ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*-_"


def _generate_password(length: int = 16) -> str:
    """Cryptographically strong password with mixed character classes."""
    while True:
        candidate = "".join(secrets.choice(_PASSWORD_ALPHABET) for _ in range(length))
        if (
            any(c.islower() for c in candidate)
            and any(c.isupper() for c in candidate)
            and any(c.isdigit() for c in candidate)
        ):
            return candidate


def _read_config() -> tuple[str, str, str, str, str | None, bool, bool]:
    email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    name = (os.environ.get("ADMIN_NAME") or "").strip()
    role = (os.environ.get("ADMIN_ROLE") or "operations").strip()
    password = os.environ.get("ADMIN_PASSWORD")
    tenant_raw = (os.environ.get("ADMIN_TENANT_ID") or "").strip()
    reset = os.environ.get("ADMIN_RESET_PASSWORD", "").strip() in {"1", "true", "yes"}

    if not email or "@" not in email:
        raise SystemExit("ADMIN_EMAIL is required and must be a valid email address.")
    if not name:
        raise SystemExit("ADMIN_NAME is required (the admin's full name).")
    if role not in _ALLOWED_ROLES:
        raise SystemExit(f"ADMIN_ROLE must be one of {sorted(_ALLOWED_ROLES)}; got {role!r}.")

    tenant_id = None
    if tenant_raw:
        if not tenant_raw.isdigit():
            raise SystemExit("ADMIN_TENANT_ID must be an integer if provided.")
        tenant_id = tenant_raw

    # Auto-generate a password only when the operator did not supply one.
    generated = False
    if not password:
        password = _generate_password()
        generated = True

    return email, name, role, password, tenant_id, generated, reset


async def create_admin() -> None:
    from sqlalchemy import select

    from app.core.database import async_session
    from app.core.security import hash_password
    from app.models.user import User

    email, name, role, password, tenant_id, generated, reset = _read_config()

    async with async_session() as db:
        existing = (
            await db.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

        password_was_set = False
        if existing is None:
            user = User(
                email=email,
                full_name=name,
                hashed_password=hash_password(password),
                role=role,
                is_active=True,
                email_setup_completed=True,
                # If we generated the password, force a rotation on first login.
                password_change_required=generated,
                tenant_id=int(tenant_id) if tenant_id is not None else None,
            )
            db.add(user)
            password_was_set = True
            action = "created"
        else:
            existing.full_name = name
            existing.role = role
            existing.is_active = True
            existing.email_setup_completed = True
            if tenant_id is not None:
                existing.tenant_id = int(tenant_id)
            # Only touch the password when explicitly asked — a routine
            # re-run must not lock out a working admin.
            if reset or os.environ.get("ADMIN_PASSWORD"):
                existing.hashed_password = hash_password(password)
                existing.password_change_required = generated
                password_was_set = True
            action = "updated"

        await db.commit()

    print()
    print("─" * 72)
    print(f"Admin {action}: {email}  (role={role})")
    if password_was_set:
        print(f"  password: {password}")
        if generated:
            print("  ⚠ auto-generated — password_change_required=True (rotate on first login)")
    else:
        print("  password: (unchanged — pass ADMIN_PASSWORD or ADMIN_RESET_PASSWORD=1 to reset)")
    print(f"  sign in at /login")
    print("─" * 72)
    logger.info("%s admin %s (role=%s)", action, email, role)


async def main() -> None:
    await create_admin()


if __name__ == "__main__":
    asyncio.run(main())
