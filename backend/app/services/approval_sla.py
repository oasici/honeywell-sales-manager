"""F-028 — approval SLA + escalation.

Pre-Round-19 ``ApprovalRule.escalation_hours`` existed but had no
runner — pending requests aged forever silently. This module wires
the existing column into a cron-callable workflow:

  1. ``annotate_due_at`` on creation: stamp ``due_at = created_at +
     rule.escalation_hours`` so we can filter by it.
  2. ``find_overdue_approvals`` cron query — returns ``pending``
     requests where ``now() > due_at`` and ``escalated_at IS NULL``.
  3. ``escalate_request`` — reassigns to the rule's escalation
     target (``delegate_to`` or the approver's manager) and bumps
     ``escalation_level``. Audit-logs each step.

Hard rule: **NEVER auto-approve on SLA breach.** A breached request
becomes more visible (banner in Cockpit, manager notification, ops
report), but the *human decision is mandatory*. The Round-19 audit
called this out explicitly — silent auto-approve is worse than
silent timeout.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OverdueApproval:
    """Pure-data row for cron emission. Decoupled from ORM so tests
    don't need a session."""

    request_id: int
    rule_id: int | None
    assigned_to: int | None
    age_hours: float
    sla_hours: int
    escalation_level: int


def compute_due_at(
    *, created_at: datetime, escalation_hours: int | None
) -> datetime | None:
    """Return the deadline timestamp, or None when the rule has no SLA."""
    if not escalation_hours or escalation_hours <= 0:
        return None
    return created_at + timedelta(hours=escalation_hours)


def is_overdue(
    *, due_at: datetime | None, now: datetime | None = None
) -> bool:
    """Pure check."""
    if due_at is None:
        return False
    now = now or datetime.now(timezone.utc)
    return now > due_at


def next_escalation_target(
    *,
    current_assignee_id: int | None,
    rule_delegate_id: int | None,
    rule_escalation_action: str | None,
    manager_id: int | None,
) -> tuple[int | None, str]:
    """Return ``(next_assignee_id, action_taken)``.

    Precedence:
      1. If the rule names a delegate, use that.
      2. Else if rule.escalation_action == ``escalate_to_manager``, use ``manager_id``.
      3. Else keep current assignee (no rerouting) but still flag for ops.

    ``auto_approve`` as ``escalation_action`` is *explicitly ignored*
    here — the Round-19 audit forbids it; we log a warning and treat
    it as ``escalate_to_manager``.
    """
    if rule_delegate_id is not None:
        return rule_delegate_id, "delegated"
    if rule_escalation_action == "auto_approve":
        logger.warning(
            "ApprovalRule has escalation_action='auto_approve'; ignoring per "
            "Round-19 policy. Treating as escalate_to_manager."
        )
        return manager_id, "escalated_to_manager"
    if rule_escalation_action == "escalate_to_manager":
        return manager_id, "escalated_to_manager"
    return current_assignee_id, "flagged_no_route"


def summarise_for_cockpit(rows: Iterable[OverdueApproval]) -> dict:
    """Aggregate counts for the Cockpit overdue badge."""
    total = 0
    by_level: dict[int, int] = {}
    oldest_hours = 0.0
    for r in rows:
        total += 1
        by_level[r.escalation_level] = by_level.get(r.escalation_level, 0) + 1
        if r.age_hours > oldest_hours:
            oldest_hours = r.age_hours
    return {
        "total_overdue": total,
        "by_escalation_level": by_level,
        "oldest_age_hours": oldest_hours,
    }
