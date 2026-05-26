"""Round-19 Phase 3 hardening tests.

Covers F-018 (approval quorum), F-026 (quote supersede),
F-027 (pricing precedence), F-028 (approval SLA).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest


# ────────────────────────────────────────────────────────────────────
# F-018 — Approval quorum
# ────────────────────────────────────────────────────────────────────


from app.services.approval_quorum import (
    Decision,
    QuorumResult,
    compute_quorum_state,
    is_duplicate_decision,
)


def test_quorum_any_one_approves_on_first_approve() -> None:
    r = compute_quorum_state(
        decisions=[Decision(decider_id=1, outcome="approve")],
        policy="any_one",
    )
    assert r.status == "approved"
    assert r.approve_count == 1


def test_quorum_any_one_stays_pending_with_no_decisions() -> None:
    r = compute_quorum_state(decisions=[], policy="any_one")
    assert r.status == "pending"


def test_quorum_all_requires_expected_count() -> None:
    r = compute_quorum_state(
        decisions=[
            Decision(decider_id=1, outcome="approve"),
            Decision(decider_id=2, outcome="approve"),
        ],
        policy="all",
        expected_approvers=3,
    )
    assert r.status == "pending"
    assert "1_more" in (r.reason or "")


def test_quorum_all_approved_when_full_set() -> None:
    r = compute_quorum_state(
        decisions=[
            Decision(decider_id=i, outcome="approve") for i in range(1, 4)
        ],
        policy="all",
        expected_approvers=3,
    )
    assert r.status == "approved"


def test_quorum_n_of_m_threshold() -> None:
    r = compute_quorum_state(
        decisions=[Decision(decider_id=1, outcome="approve")],
        policy="n_of_m",
        quorum_n=2,
    )
    assert r.status == "pending"
    r2 = compute_quorum_state(
        decisions=[
            Decision(decider_id=1, outcome="approve"),
            Decision(decider_id=2, outcome="approve"),
        ],
        policy="n_of_m",
        quorum_n=2,
    )
    assert r2.status == "approved"


def test_quorum_rejection_is_sticky_under_any_policy() -> None:
    # Under any policy, one reject wins over any number of approves.
    for policy in ("any_one", "all", "n_of_m"):
        r = compute_quorum_state(
            decisions=[
                Decision(decider_id=1, outcome="approve"),
                Decision(decider_id=2, outcome="approve"),
                Decision(decider_id=3, outcome="reject"),
            ],
            policy=policy,
            quorum_n=2,
            expected_approvers=2,
        )
        assert r.status == "rejected", f"policy {policy} failed sticky reject"


def test_quorum_unknown_policy_falls_back_to_pending() -> None:
    """Safety: don't silently approve under an unrecognised policy."""
    r = compute_quorum_state(
        decisions=[Decision(decider_id=1, outcome="approve")],
        policy="custom_made_up_policy",
    )
    assert r.status == "pending"
    assert "unknown_policy" in (r.reason or "")


def test_duplicate_decision_detection() -> None:
    existing = [Decision(decider_id=1, outcome="approve")]
    assert is_duplicate_decision(existing, decider_id=1) is True
    assert is_duplicate_decision(existing, decider_id=2) is False


# ────────────────────────────────────────────────────────────────────
# F-026 — Quote supersede
# ────────────────────────────────────────────────────────────────────


from app.services.quote_supersede import (
    QuoteSupersedeError,
    can_supersede,
    is_live,
    mark_superseded,
)


@dataclass
class _StubQuote:
    id: int = 1
    status: str = "sent"
    superseded_by_id: int | None = None
    superseded_at: datetime | None = None


@pytest.mark.parametrize("status", ["sent", "declined", "expired"])
def test_can_supersede_allows_sendable_statuses(status: str) -> None:
    ok, reason = can_supersede(status)
    assert ok and reason is None


@pytest.mark.parametrize("status", ["accepted", "cancelled"])
def test_can_supersede_refuses_frozen_statuses(status: str) -> None:
    ok, reason = can_supersede(status)
    assert ok is False
    assert reason and "frozen" in reason


def test_can_supersede_refuses_draft() -> None:
    ok, reason = can_supersede("draft")
    assert ok is False
    assert reason == "draft_should_be_edited_in_place"


def test_mark_superseded_writes_back_pointers() -> None:
    parent = _StubQuote(id=1, status="sent")
    child = _StubQuote(id=2, status="draft")
    mark_superseded(parent, child)
    assert parent.superseded_by_id == 2
    assert parent.superseded_at is not None
    # is_live now follows superseded_by_id, not status.
    assert is_live(parent) is False
    assert is_live(child) is True


def test_mark_superseded_raises_on_accepted_parent() -> None:
    parent = _StubQuote(status="accepted")
    child = _StubQuote(id=2)
    with pytest.raises(QuoteSupersedeError, match="frozen"):
        mark_superseded(parent, child)


# ────────────────────────────────────────────────────────────────────
# F-027 — Pricing precedence
# ────────────────────────────────────────────────────────────────────


from app.services.pricing_resolver import (
    PriceCandidate,
    PricingResolutionError,
    resolve_price,
    precedence_index,
    SRC_CAMPAIGN,
    SRC_CONTRACT,
    SRC_TIER,
    SRC_CATALOG,
)


def _cand(amount, source, ref=None) -> PriceCandidate:
    return PriceCandidate(
        amount=Decimal(str(amount)),
        currency="TRY",
        source=source,
        ref=ref,
    )


def test_price_resolver_picks_campaign_when_present() -> None:
    r = resolve_price([
        _cand(100, SRC_CATALOG),
        _cand(80, SRC_TIER, ref="Platinum"),
        _cand(70, SRC_CONTRACT, ref="C-42"),
        _cand(60, SRC_CAMPAIGN, ref="PROMO-Q3"),
    ])
    assert r.source == SRC_CAMPAIGN
    assert r.amount == Decimal("60")


def test_price_resolver_falls_through_to_catalog() -> None:
    r = resolve_price([_cand(100, SRC_CATALOG)])
    assert r.source == SRC_CATALOG


def test_price_resolver_ignores_zero_candidates() -> None:
    """Catalog default of 0 = unconfigured, not free."""
    r = resolve_price([
        _cand(0, SRC_CATALOG),
        _cand(80, SRC_TIER, ref="Gold"),
    ])
    assert r.source == SRC_TIER


def test_price_resolver_raises_when_no_valid_candidate() -> None:
    with pytest.raises(PricingResolutionError):
        resolve_price([_cand(0, SRC_CATALOG)])


def test_precedence_index_orders_correctly() -> None:
    assert precedence_index(SRC_CAMPAIGN) < precedence_index(SRC_CONTRACT)
    assert precedence_index(SRC_CONTRACT) < precedence_index(SRC_TIER)
    assert precedence_index(SRC_TIER) < precedence_index(SRC_CATALOG)
    assert precedence_index("unknown") == 99


# ────────────────────────────────────────────────────────────────────
# F-028 — Approval SLA
# ────────────────────────────────────────────────────────────────────


from app.services.approval_sla import (
    OverdueApproval,
    compute_due_at,
    is_overdue,
    next_escalation_target,
    summarise_for_cockpit,
)


def test_compute_due_at_returns_none_when_no_sla() -> None:
    assert compute_due_at(created_at=datetime.now(timezone.utc), escalation_hours=None) is None
    assert compute_due_at(created_at=datetime.now(timezone.utc), escalation_hours=0) is None


def test_compute_due_at_adds_hours() -> None:
    base = datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc)
    due = compute_due_at(created_at=base, escalation_hours=24)
    assert due == base + timedelta(hours=24)


def test_is_overdue_respects_due_at() -> None:
    now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=1)
    assert is_overdue(due_at=past, now=now) is True
    assert is_overdue(due_at=future, now=now) is False
    assert is_overdue(due_at=None, now=now) is False


def test_next_escalation_prefers_delegate() -> None:
    nxt, action = next_escalation_target(
        current_assignee_id=10,
        rule_delegate_id=20,
        rule_escalation_action=None,
        manager_id=30,
    )
    assert nxt == 20
    assert action == "delegated"


def test_next_escalation_uses_manager_when_no_delegate() -> None:
    nxt, action = next_escalation_target(
        current_assignee_id=10,
        rule_delegate_id=None,
        rule_escalation_action="escalate_to_manager",
        manager_id=30,
    )
    assert nxt == 30
    assert action == "escalated_to_manager"


def test_next_escalation_refuses_auto_approve() -> None:
    """Round-19 rule: never auto-approve on SLA breach. The function
    treats auto_approve as escalate_to_manager."""
    nxt, action = next_escalation_target(
        current_assignee_id=10,
        rule_delegate_id=None,
        rule_escalation_action="auto_approve",
        manager_id=30,
    )
    assert action == "escalated_to_manager"
    assert nxt == 30


def test_next_escalation_falls_back_to_no_route() -> None:
    nxt, action = next_escalation_target(
        current_assignee_id=10,
        rule_delegate_id=None,
        rule_escalation_action=None,
        manager_id=None,
    )
    assert nxt == 10  # unchanged
    assert action == "flagged_no_route"


def test_summarise_for_cockpit() -> None:
    rows = [
        OverdueApproval(request_id=1, rule_id=10, assigned_to=5, age_hours=30, sla_hours=24, escalation_level=1),
        OverdueApproval(request_id=2, rule_id=10, assigned_to=5, age_hours=8, sla_hours=4, escalation_level=2),
        OverdueApproval(request_id=3, rule_id=11, assigned_to=6, age_hours=50, sla_hours=24, escalation_level=1),
    ]
    summary = summarise_for_cockpit(rows)
    assert summary["total_overdue"] == 3
    assert summary["by_escalation_level"] == {1: 2, 2: 1}
    assert summary["oldest_age_hours"] == 50
