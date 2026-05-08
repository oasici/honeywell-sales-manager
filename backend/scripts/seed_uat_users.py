"""Seed UAT user accounts covering every role + permission shape.

Creates 5 accounts so a single tester can sign in as any role to verify
end-to-end behavior without juggling SQL:

  • UAT Admin (sales_manager, top of the org tree, sees everything)
  • UAT Manager (sales_manager, reports to the admin — multi-manager flows)
  • UAT Rep A (sales_rep, reports to UAT Manager — single-rep visibility)
  • UAT Rep B (sales_rep, reports to UAT Manager — peer to Rep A,
    used to verify cross-rep isolation)
  • UAT Ops (operations — KVKK / retention / breaches surfaces)

Idempotent: re-running the script updates the password + role +
``manager_id`` to match this script's source of truth, so credentials
never drift between environments.

Usage (local dev DB, the .env DATABASE_URL):
    cd backend
    PYTHONPATH=. python -m scripts.seed_uat_users

Usage (point at sandbox or staging):
    DATABASE_URL='postgresql+asyncpg://user:pass@host:5432/dbname' \
        PYTHONPATH=. python -m scripts.seed_uat_users

The script never seeds business data — pair with seed_demo_data.py /
seed_uat_data.py if you also need fixtures.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from pathlib import Path

# Add backend to path so ``app.*`` imports resolve from the script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-5s %(message)s")
logger = logging.getLogger("seed_uat_users")


@dataclass(frozen=True)
class UatUser:
    email: str
    full_name: str
    role: str  # sales_manager | sales_rep | operations
    password: str
    reports_to_email: str | None = None  # filled in via manager_id after first pass


# Single source of truth — change here, re-run script, accounts converge.
UAT_USERS: tuple[UatUser, ...] = (
    # Pre-existing demo admin elevated to sales_manager so UAT credentials
    # work even on environments seeded by ``seed_demo_data.py``.
    UatUser(
        email="admin@honeywell.com",
        full_name="UAT Admin",
        role="sales_manager",
        password="Admin123!",
    ),
    UatUser(
        email="uat-admin@honeywell.com",
        full_name="UAT Admin",
        role="sales_manager",
        password="UatAdmin!2026",
    ),
    UatUser(
        email="uat-manager@honeywell.com",
        full_name="UAT Manager",
        role="sales_manager",
        password="UatManager!2026",
        reports_to_email="uat-admin@honeywell.com",
    ),
    UatUser(
        email="uat-rep-a@honeywell.com",
        full_name="UAT Rep A",
        role="sales_rep",
        password="UatRepA!2026",
        reports_to_email="uat-manager@honeywell.com",
    ),
    UatUser(
        email="uat-rep-b@honeywell.com",
        full_name="UAT Rep B",
        role="sales_rep",
        password="UatRepB!2026",
        reports_to_email="uat-manager@honeywell.com",
    ),
    UatUser(
        email="uat-ops@honeywell.com",
        full_name="UAT Ops",
        role="operations",
        password="UatOps!2026",
        reports_to_email="uat-admin@honeywell.com",
    ),
)


async def seed_users() -> None:
    from sqlalchemy import select

    from app.core.database import async_session
    from app.core.security import hash_password
    from app.models.user import User

    async with async_session() as db:
        # Pass 1: upsert all users so their IDs exist before we wire managers.
        for spec in UAT_USERS:
            existing = (
                await db.execute(select(User).where(User.email == spec.email))
            ).scalar_one_or_none()
            if existing is None:
                user = User(
                    email=spec.email,
                    full_name=spec.full_name,
                    hashed_password=hash_password(spec.password),
                    role=spec.role,
                    is_active=True,
                    email_setup_completed=True,
                    password_change_required=False,
                )
                db.add(user)
                logger.info("created %s (%s)", spec.email, spec.role)
            else:
                existing.full_name = spec.full_name
                existing.role = spec.role
                existing.hashed_password = hash_password(spec.password)
                existing.is_active = True
                existing.email_setup_completed = True
                existing.password_change_required = False
                logger.info("updated %s (%s)", spec.email, spec.role)
        await db.flush()

        # Pass 2: wire ``manager_id`` from email-keyed reporting links.
        users_by_email: dict[str, User] = {}
        for spec in UAT_USERS:
            user = (
                await db.execute(select(User).where(User.email == spec.email))
            ).scalar_one()
            users_by_email[spec.email] = user

        for spec in UAT_USERS:
            if spec.reports_to_email is None:
                users_by_email[spec.email].manager_id = None
                continue
            manager = users_by_email.get(spec.reports_to_email)
            if manager is None:
                logger.warning(
                    "manager %s for %s not found — leaving manager_id null",
                    spec.reports_to_email,
                    spec.email,
                )
                continue
            users_by_email[spec.email].manager_id = manager.id

        await db.commit()

        # Print a copy-pasteable credentials block.
        print()
        print("─" * 72)
        print("UAT credentials — sign in at /login with any of these accounts:")
        print("─" * 72)
        for spec in UAT_USERS:
            print(f"  role={spec.role:<14}  email={spec.email:<28}  password={spec.password}")
        print("─" * 72)


async def main() -> None:
    await seed_users()


if __name__ == "__main__":
    asyncio.run(main())
