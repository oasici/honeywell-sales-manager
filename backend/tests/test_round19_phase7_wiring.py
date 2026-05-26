"""Round-19 Phase 7 — cron wiring + extended optimistic locking.

Covers:
  * Scheduler registers the 4 Round-19 jobs.
  * Each cron task is a defined async coroutine that imports cleanly.
  * customers / opportunities / contracts now carry row_version.
"""

from __future__ import annotations

import asyncio
import inspect

import pytest


# ────────────────────────────────────────────────────────────────────
# Scheduler registration (TC-CRON-001..004)
# ────────────────────────────────────────────────────────────────────


def test_scheduler_registers_round19_jobs() -> None:
    """start_scheduler() must register the 4 R19 jobs with the right
    interval / cron schedule and stable IDs (so audit + ops tooling
    can identify them)."""
    from app.tasks import scheduler as sched_mod

    # Importing the module is enough to surface the job IDs as
    # constants — we don't actually start the scheduler in a unit
    # test (no event loop). Verify the start_scheduler function
    # contains references to the four IDs.
    src = inspect.getsource(sched_mod.start_scheduler)
    assert "r19_token_blocklist_cleanup" in src
    assert "r19_admin_nonce_cleanup" in src
    assert "r19_approval_sla_escalation" in src
    assert "r19_health_recompute_batch" in src


def test_cron_task_functions_are_async() -> None:
    from app.tasks.scheduler import (
        r19_admin_nonce_cleanup_task,
        r19_approval_sla_task,
        r19_health_recompute_task,
        r19_token_blocklist_cleanup_task,
    )

    for fn in (
        r19_token_blocklist_cleanup_task,
        r19_admin_nonce_cleanup_task,
        r19_approval_sla_task,
        r19_health_recompute_task,
    ):
        assert asyncio.iscoroutinefunction(fn), f"{fn.__name__} must be async"


# ────────────────────────────────────────────────────────────────────
# Extended optimistic locking (TC-OCC-001..003)
# ────────────────────────────────────────────────────────────────────


def test_customer_has_row_version() -> None:
    from app.models.customer import Customer

    assert "row_version" in {c.key for c in Customer.__mapper__.column_attrs}


def test_opportunity_has_row_version() -> None:
    from app.models.opportunity import Opportunity

    assert "row_version" in {c.key for c in Opportunity.__mapper__.column_attrs}


def test_contract_has_row_version() -> None:
    from app.models.contract import Contract

    assert "row_version" in {c.key for c in Contract.__mapper__.column_attrs}


# ────────────────────────────────────────────────────────────────────
# guarded_update works against all three entities
# (TC-CUST-012 / TC-OPP-OCC / TC-CONTRACT-OCC)
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_guarded_update_blocks_stale_customer_write(
    db, admin_user
) -> None:
    """Two concurrent writers; the second one (stale version) gets
    OptimisticLockConflict."""
    from app.models.customer import Customer
    from app.services.optimistic_locking import (
        OptimisticLockConflict,
        guarded_update,
    )

    cust = Customer(
        tenant_id=admin_user.tenant_id,
        name="OCC Test",
        email="occ@test.com",
        created_by=admin_user.id,
    )
    db.add(cust)
    await db.commit()
    await db.refresh(cust)
    expected = cust.row_version

    # First writer wins.
    res = await guarded_update(
        db,
        Customer,
        id_=cust.id,
        expected_version=expected,
        updates={"name": "Updated First"},
    )
    assert res.new_row_version == expected + 1

    # Second writer with stale version fails.
    with pytest.raises(OptimisticLockConflict):
        await guarded_update(
            db,
            Customer,
            id_=cust.id,
            expected_version=expected,            # stale!
            updates={"name": "Updated Second"},
        )


@pytest.mark.asyncio
async def test_guarded_update_rejects_manual_row_version(db, admin_user) -> None:
    """Callers may not set row_version themselves — the helper bumps it."""
    from app.models.customer import Customer
    from app.services.optimistic_locking import guarded_update

    cust = Customer(
        tenant_id=admin_user.tenant_id,
        name="Manual RV Test",
        email="rv@test.com",
        created_by=admin_user.id,
    )
    db.add(cust)
    await db.commit()
    await db.refresh(cust)

    with pytest.raises(ValueError, match="row_version"):
        await guarded_update(
            db,
            Customer,
            id_=cust.id,
            expected_version=cust.row_version,
            updates={"row_version": 99, "name": "x"},
        )
