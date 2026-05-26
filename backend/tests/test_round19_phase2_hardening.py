"""Round-19 Phase 2 hardening tests.

Covers F-010, F-013, F-015, F-017, F-029.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest


# ────────────────────────────────────────────────────────────────────
# F-015 — Workflow rule cycle + depth detection
# ────────────────────────────────────────────────────────────────────


from app.services.workflow_cycle_detector import (
    MAX_DEPTH,
    RuleExecutionContext,
    WorkflowCycleDetected,
    WorkflowDepthExceeded,
    detect_static_cycles,
)


def test_rule_context_allows_normal_chain() -> None:
    ctx = RuleExecutionContext()
    for rid in [1, 2, 3]:
        ctx.enter(rid)
    assert ctx.depth == 3
    ctx.exit_(3)
    assert ctx.depth == 2


def test_rule_context_blocks_cycle() -> None:
    ctx = RuleExecutionContext()
    ctx.enter(1)
    ctx.enter(2)
    with pytest.raises(WorkflowCycleDetected):
        ctx.enter(1)         # re-fire of rule 1 in same chain


def test_rule_context_blocks_depth() -> None:
    ctx = RuleExecutionContext(max_depth=3)
    ctx.enter(1)
    ctx.enter(2)
    ctx.enter(3)
    with pytest.raises(WorkflowDepthExceeded):
        ctx.enter(4)


def test_rule_context_remembers_visited_after_exit() -> None:
    """exit_() restores depth but NOT visited_rules — that's what
    blocks ``A → B → A`` patterns where A finishes before A retries."""
    ctx = RuleExecutionContext()
    ctx.enter(1)
    ctx.exit_(1)
    assert ctx.depth == 0
    with pytest.raises(WorkflowCycleDetected):
        ctx.enter(1)


@dataclass
class _StubRule:
    id: int
    trigger_event: str
    action_event: str


def test_static_cycle_detector_finds_simple_loop() -> None:
    """A: tier_changed → tier_changed (self-loop)."""
    a = _StubRule(id=1, trigger_event="tier_changed", action_event="tier_changed")
    cycles = detect_static_cycles([a])
    assert len(cycles) == 1
    assert 1 in cycles[0]


def test_static_cycle_detector_finds_a_b_a() -> None:
    a = _StubRule(id=1, trigger_event="status_x", action_event="status_y")
    b = _StubRule(id=2, trigger_event="status_y", action_event="status_x")
    cycles = detect_static_cycles([a, b])
    assert len(cycles) >= 1
    # Either {1,2} ordering is fine; just verify both IDs appear.
    flat = {rid for c in cycles for rid in c}
    assert {1, 2}.issubset(flat)


def test_static_cycle_detector_passes_clean_chain() -> None:
    a = _StubRule(id=1, trigger_event="created", action_event="reviewed")
    b = _StubRule(id=2, trigger_event="reviewed", action_event="approved")
    assert detect_static_cycles([a, b]) == []


# ────────────────────────────────────────────────────────────────────
# F-017 — Optimistic locking
# ────────────────────────────────────────────────────────────────────


from app.services.optimistic_locking import OptimisticLockConflict


def test_optimistic_lock_conflict_carries_metadata() -> None:
    exc = OptimisticLockConflict(model="Quote", id_=42, expected=5)
    assert exc.model == "Quote"
    assert exc.id_ == 42
    assert exc.expected == 5
    assert "Quote" in str(exc)
    assert "42" in str(exc)


def test_optimistic_lock_helper_rejects_manual_row_version() -> None:
    """``row_version`` must be bumped by the helper, never the caller."""
    from app.services.optimistic_locking import guarded_update

    # Construct a never-awaited coroutine by trying to pass row_version
    # in updates — the helper raises before any DB hit.
    import asyncio

    class _NotAQuote:
        __name__ = "NotAQuote"

    async def go() -> None:
        await guarded_update(
            db=None,
            model=_NotAQuote,
            id_=1,
            expected_version=1,
            updates={"row_version": 2},   # forbidden
        )

    with pytest.raises(ValueError, match="row_version"):
        asyncio.get_event_loop().run_until_complete(go())


# ────────────────────────────────────────────────────────────────────
# F-029 — per-tenant auto-quote threshold
# ────────────────────────────────────────────────────────────────────


from app.services.email_processing_service import _auto_quote_eligible
from app.services.tenant_settings_service import TenantConfig, estimate_quote_total


class _GateStub:
    def __init__(
        self,
        sender_auth_status: str = "pass",
        attachment_pages_truncated: bool = False,
        first_time_sender: bool = False,
    ) -> None:
        self.sender_auth_status = sender_auth_status
        self.attachment_pages_truncated = attachment_pages_truncated
        self.first_time_sender = first_time_sender


def _parsed_with_value(unit_price: float, qty: int = 1, n: int = 1) -> dict:
    return {
        "parts": [
            {
                "part_code": f"C7061A101{i}",
                "catalog_status": "exact",
                "unit_price": unit_price,
                "quantity": qty,
            }
            for i in range(n)
        ]
    }


def test_estimate_quote_total_sums_line_items() -> None:
    parsed = _parsed_with_value(1000, qty=3, n=2)
    assert estimate_quote_total(parsed) == Decimal("6000")


def test_estimate_quote_total_returns_zero_when_no_prices() -> None:
    parsed = {"parts": [{"part_code": "x", "catalog_status": "exact"}]}
    assert estimate_quote_total(parsed) == Decimal("0")


def test_gate_blocks_when_total_above_tenant_threshold() -> None:
    cfg = TenantConfig.defaults(1)
    cfg_with_cap = TenantConfig(
        tenant_id=cfg.tenant_id,
        auto_quote_max_amount=Decimal("5000"),
        auto_quote_currency=cfg.auto_quote_currency,
        base_currency=cfg.base_currency,
        ocr_max_pages=cfg.ocr_max_pages,
        ai_monthly_quota_usd=cfg.ai_monthly_quota_usd,
        at_risk_threshold=40,
    )
    eligible, reason = _auto_quote_eligible(
        _GateStub(), _parsed_with_value(10000, qty=1), tenant_config=cfg_with_cap
    )
    assert eligible is False
    assert reason == "value_above_threshold"


def test_gate_allows_when_total_under_tenant_threshold() -> None:
    cfg = TenantConfig(
        tenant_id=1,
        auto_quote_max_amount=Decimal("5000"),
        auto_quote_currency="TRY",
        base_currency="TRY",
        ocr_max_pages=5,
        ai_monthly_quota_usd=None,
        at_risk_threshold=40,
    )
    eligible, reason = _auto_quote_eligible(
        _GateStub(), _parsed_with_value(1000, qty=1), tenant_config=cfg
    )
    assert eligible is True
    assert reason is None


def test_gate_skips_amount_check_when_no_cap_configured() -> None:
    cfg = TenantConfig.defaults(1)  # auto_quote_max_amount=None
    eligible, reason = _auto_quote_eligible(
        _GateStub(), _parsed_with_value(999_999), tenant_config=cfg
    )
    assert eligible is True
    assert reason is None


def test_gate_skips_amount_check_when_estimate_is_zero() -> None:
    """Parser may not surface prices yet — don't fire the cap on $0."""
    cfg = TenantConfig(
        tenant_id=1,
        auto_quote_max_amount=Decimal("1"),
        auto_quote_currency="TRY",
        base_currency="TRY",
        ocr_max_pages=5,
        ai_monthly_quota_usd=None,
        at_risk_threshold=40,
    )
    parsed = {"parts": [{"part_code": "x", "catalog_status": "exact"}]}
    eligible, reason = _auto_quote_eligible(_GateStub(), parsed, tenant_config=cfg)
    assert eligible is True
    assert reason is None


# ────────────────────────────────────────────────────────────────────
# F-010 — Approval rule self-disable guard
# ────────────────────────────────────────────────────────────────────


from app.services.approval_self_disable_guard import (
    EditClassification,
    classify_rule_edit,
)


@dataclass
class _StubRule_F010:
    id: int = 1
    tenant_id: int = 1
    is_active: bool = True
    threshold_value: float = 30
    threshold_operator: str = "gt"
    approver_role: str | None = "sales_manager"
    approver_user_id: int | None = None
    escalation_action: str | None = None


def test_classify_allows_neutral_rename() -> None:
    r = _StubRule_F010()
    c = classify_rule_edit(r, {"name": "Renamed"}, editor_id=99, editor_role="sales_manager")
    assert c.decision == "allow"


def test_classify_flags_self_disable() -> None:
    r = _StubRule_F010()
    c = classify_rule_edit(
        r, {"is_active": False}, editor_id=99, editor_role="sales_manager"
    )
    assert c.decision == "meta"
    assert "disable" in c.relaxations


def test_classify_allows_disable_by_non_gated_role() -> None:
    """A sales_rep (not the approver) disabling the rule is rare but
    structurally fine — backend role check already blocks it at the
    permission layer; the meta-flow only triggers when the editor is
    themselves the approver."""
    r = _StubRule_F010()
    c = classify_rule_edit(
        r, {"is_active": False}, editor_id=99, editor_role="sales_rep"
    )
    assert c.decision == "allow"


def test_classify_flags_threshold_relax() -> None:
    r = _StubRule_F010()    # threshold 30
    c = classify_rule_edit(
        r, {"threshold_value": 99}, editor_id=99, editor_role="sales_manager"
    )
    assert c.decision == "meta"
    assert "threshold_raised" in c.relaxations


def test_classify_flags_operator_weakened() -> None:
    r = _StubRule_F010(threshold_operator="gt")
    c = classify_rule_edit(
        r, {"threshold_operator": "gte"}, editor_id=99, editor_role="sales_manager"
    )
    assert c.decision == "meta"


def test_classify_flags_approver_removed() -> None:
    r = _StubRule_F010(approver_user_id=99)
    c = classify_rule_edit(
        r,
        {"approver_role": None, "approver_user_id": None},
        editor_id=99,
        editor_role="sales_manager",
    )
    assert c.decision == "meta"
    assert "approver_removed" in c.relaxations


def test_classify_flags_auto_approve_introduced() -> None:
    r = _StubRule_F010()
    c = classify_rule_edit(
        r,
        {"escalation_action": "auto_approve"},
        editor_id=99,
        editor_role="sales_manager",
    )
    assert c.decision == "meta"
    assert "auto_approve_added" in c.relaxations


# ────────────────────────────────────────────────────────────────────
# F-013 — JTI blocklist (sanity-only; full integration needs DB fixture)
# ────────────────────────────────────────────────────────────────────


def test_token_blocklist_module_imports_and_exposes_api() -> None:
    """Smoke test that the module surface is intact — full async
    PG-fixture tests live in ``tests/test_token_blocklist_integration.py``
    once a future PR adds them (out of scope for the Phase 2 pure-code
    batch)."""
    from app.services import token_blocklist

    assert callable(token_blocklist.revoke_jti_persistent)
    assert callable(token_blocklist.is_jti_revoked_persistent)
    assert callable(token_blocklist.revoke_all_for_user)
    assert callable(token_blocklist.cleanup_expired_blocklist)
