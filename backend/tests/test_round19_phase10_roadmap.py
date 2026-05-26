"""Round-19 Phase 10 — additional roadmap items.

D-013 — Workflow cycle/depth guard wired into WorkflowService.evaluate_event
"""

from __future__ import annotations

import json

import pytest


# ────────────────────────────────────────────────────────────────────
# D-013 — Workflow cycle guard at runtime
# ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_workflow_evaluate_uses_context_to_block_cycles(db, admin_user) -> None:
    """Pass a context with rule N already visited → service refuses to
    re-fire N and logs a blocked_cycle row."""
    from sqlalchemy import text

    from app.models.workflow_rule import WorkflowRule
    from app.services.workflow_cycle_detector import RuleExecutionContext
    from app.services.workflow_service import WorkflowService

    rule = WorkflowRule(
        tenant_id=admin_user.tenant_id,
        name="Cycle Stub",
        entity_type="customer",
        trigger_event="status_changed",
        conditions_json=None,
        actions_json=json.dumps([{"type": "field_update", "field": "x", "value": "y"}]),
        is_active=True,
        created_by=admin_user.id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)

    ctx = RuleExecutionContext()
    ctx.enter(rule.id)             # simulate "already fired"

    svc = WorkflowService(db)
    executed = await svc.evaluate_event(
        entity_type="customer",
        trigger_event="status_changed",
        entity_data={"x": "y"},
        ctx=ctx,
    )
    # The cycle guard blocked the only matching rule → 0 executed.
    assert executed == 0

    # And a log row should have been written.
    rows = (
        await db.execute(
            text(
                "SELECT outcome FROM workflow_execution_log "
                "WHERE rule_id = :rid"
            ),
            {"rid": rule.id},
        )
    ).all()
    assert any(r[0] == "blocked_cycle" for r in rows)


@pytest.mark.asyncio
async def test_workflow_evaluate_uses_context_to_block_depth(db, admin_user) -> None:
    """A context at MAX_DEPTH refuses to fire the next rule."""
    import json

    from app.models.workflow_rule import WorkflowRule
    from app.services.workflow_cycle_detector import MAX_DEPTH, RuleExecutionContext
    from app.services.workflow_service import WorkflowService

    rule = WorkflowRule(
        tenant_id=admin_user.tenant_id,
        name="Depth Stub",
        entity_type="customer",
        trigger_event="depth_test",
        conditions_json=None,
        actions_json=json.dumps([{"type": "field_update"}]),
        is_active=True,
        created_by=admin_user.id,
    )
    db.add(rule)
    await db.commit()

    ctx = RuleExecutionContext()
    # Push the chain to MAX_DEPTH without entering this rule.
    for fake_id in range(100, 100 + MAX_DEPTH):
        ctx.enter(fake_id)

    svc = WorkflowService(db)
    executed = await svc.evaluate_event(
        entity_type="customer",
        trigger_event="depth_test",
        entity_data={},
        ctx=ctx,
    )
    assert executed == 0


@pytest.mark.asyncio
async def test_workflow_evaluate_succeeds_under_clean_context(db, admin_user) -> None:
    """No context = fresh; rule fires normally."""
    import json

    from app.models.workflow_rule import WorkflowRule
    from app.services.workflow_service import WorkflowService

    rule = WorkflowRule(
        tenant_id=admin_user.tenant_id,
        name="Happy Path",
        entity_type="customer",
        trigger_event="clean_event",
        conditions_json=None,
        # field_update is a no-op action (just logs) so this won't
        # touch any other tables.
        actions_json=json.dumps([{"type": "field_update"}]),
        is_active=True,
        created_by=admin_user.id,
    )
    db.add(rule)
    await db.commit()

    svc = WorkflowService(db)
    executed = await svc.evaluate_event(
        entity_type="customer",
        trigger_event="clean_event",
        entity_data={},
    )
    assert executed == 1
