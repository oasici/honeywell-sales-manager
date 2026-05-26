"""F-018 — approval quorum aggregation.

``ApprovalRule.quorum_policy`` decides how a request transitions from
``pending`` to ``approved`` / ``rejected`` once one-or-more approvers
weigh in. Three policies:

  * ``any_one``  — first approve wins; any reject wins.
  * ``all``      — all named approvers must approve; any reject rejects.
  * ``n_of_m``   — at least ``quorum_n`` approves out of M approvers.

Every individual decision lands in ``approval_decisions`` (one row
per (request, decider) pair, enforced by a UNIQUE constraint so two
clicks from the same user can't double-count). The aggregate state
is recomputed from the ledger every time a new decision arrives.

Conflict resolution: rejection is *sticky*. Once any approver rejects,
no future approve can unstick it — the request flips to ``rejected``
even if quorum-n approvals also exist. This matches enterprise audit
intent: a single "this is wrong" should never be overridden by N
other "looks fine"s.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Decision:
    """A single approver's vote."""
    decider_id: int
    outcome: str           # "approve" | "reject"


@dataclass(frozen=True)
class QuorumResult:
    """Outcome of aggregating decisions under a quorum policy."""
    status: str            # "pending" | "approved" | "rejected"
    approve_count: int
    reject_count: int
    reason: str | None     # short code for the UI / audit log


def compute_quorum_state(
    *,
    decisions: Iterable[Decision],
    policy: str,
    quorum_n: int | None = None,
    expected_approvers: int | None = None,
) -> QuorumResult:
    """Reduce decisions to a single status under ``policy``.

    ``expected_approvers`` is the *total* approver count for ``policy='all'``
    and the ``M`` in ``n_of_m``. If callers don't know M (e.g. open-ended
    role-based rules), policy ``all`` collapses to ``any_one`` and
    ``n_of_m`` requires quorum_n approves.
    """
    approves = [d for d in decisions if d.outcome == "approve"]
    rejects = [d for d in decisions if d.outcome == "reject"]
    approve_count = len(approves)
    reject_count = len(rejects)

    # Rejection is sticky.
    if reject_count > 0:
        return QuorumResult(
            status="rejected",
            approve_count=approve_count,
            reject_count=reject_count,
            reason="rejection_recorded",
        )

    policy_l = policy.lower()
    if policy_l == "any_one":
        if approve_count >= 1:
            return QuorumResult("approved", approve_count, 0, "any_one_satisfied")
        return QuorumResult("pending", 0, 0, "awaiting_first_approve")

    if policy_l == "all":
        if expected_approvers and approve_count >= expected_approvers:
            return QuorumResult("approved", approve_count, 0, "all_approved")
        if not expected_approvers and approve_count >= 1:
            # Unknown M → degrade to any_one with audit note.
            return QuorumResult("approved", approve_count, 0, "any_one_degraded")
        return QuorumResult(
            "pending", approve_count, 0,
            f"awaiting_{(expected_approvers or 0) - approve_count}_more",
        )

    if policy_l == "n_of_m":
        need = int(quorum_n or 1)
        if approve_count >= need:
            return QuorumResult("approved", approve_count, 0, "quorum_met")
        return QuorumResult(
            "pending", approve_count, 0,
            f"awaiting_{need - approve_count}_more",
        )

    # Unknown policy — fail safe to pending so manual intervention
    # is forced, never silently approve.
    return QuorumResult(
        "pending", approve_count, reject_count,
        f"unknown_policy:{policy}",
    )


def is_duplicate_decision(
    decisions: Iterable[Decision], *, decider_id: int
) -> bool:
    """Return True iff this decider already voted on this request.

    Backed by the UNIQUE constraint ``(request_id, decider_id)`` on
    ``approval_decisions`` — this Python check exists for friendly
    error messages before the DB raises IntegrityError.
    """
    return any(d.decider_id == decider_id for d in decisions)
