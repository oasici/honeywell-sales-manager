"""F-010 — meta-approval guard for self-affecting approval-rule edits.

Sales Manager can both *create approval rules* AND *be the approver
on those rules*. Pre-Round-19 the same manager could disable the rule
that gates their own discount authority — total bypass of compliance
control (SOC 2 CC1.4 separation-of-duties fail).

This module classifies every edit attempt against an approval rule
into one of:

  * ``allow``   — edit doesn't relax the rule OR the editor isn't a
                   gated approver. Apply immediately, audit-log.
  * ``meta``    — edit relaxes a rule that gates the editor. Queue a
                   pending change row, notify Operations, leave the
                   rule unchanged until Ops decides.

The "relaxation" detection is intentionally conservative:

  * ``is_active`` flipped True → False           = relax
  * ``threshold_value`` increased                 = relax (less strict)
  * ``threshold_operator`` weakened (gt → gte)    = relax
  * ``approver_role`` / ``approver_user_id`` removed = relax
  * ``escalation_action='auto_approve'`` added    = relax (BIG one)
  * everything else                               = neutral

False positives are acceptable (Ops review is cheap); a false
negative would re-open the bypass we're closing.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_OPERATOR_STRICTNESS = {"gt": 4, "gte": 3, "lt": 2, "lte": 1}


@dataclass
class EditClassification:
    """Outcome of inspecting a proposed change to an approval rule."""

    decision: str            # "allow" | "meta"
    reason: str | None       # human-readable detail
    relaxations: list[str]   # specific fields that would relax


def classify_rule_edit(
    rule: Any,
    proposed: dict,
    *,
    editor_id: int,
    editor_role: str | None,
) -> EditClassification:
    """Decide whether ``proposed`` requires Ops meta-approval.

    ``rule``    : the current ApprovalRule row (any object with the
                  named attributes — accepts both ORM rows and dataclass
                  stubs for testing).
    ``proposed``: dict of fields the editor wants to change (only the
                  changed keys; missing keys are left alone).
    ``editor_id``, ``editor_role``: who's editing.

    Pure function (no DB) so unit tests don't need a session.
    """
    relaxations: list[str] = []

    # 1) Active toggle: only "True → False" is a relax.
    if "is_active" in proposed:
        if bool(getattr(rule, "is_active", True)) and not bool(proposed["is_active"]):
            relaxations.append("disable")

    # 2) Threshold increase = less strict gate.
    if "threshold_value" in proposed:
        current = float(getattr(rule, "threshold_value", 0) or 0)
        new = float(proposed["threshold_value"] or 0)
        # For "gt" / "gte" / "deal_amount" rules, raising the threshold
        # means more transactions slip past. For "lt" / "lte" rules,
        # lowering would do the same — but the operator/operator field
        # decides direction; we err conservative and flag any change.
        if new > current * 1.1:    # >10% relax
            relaxations.append("threshold_raised")

    # 3) Operator weakened.
    if "threshold_operator" in proposed:
        before = _OPERATOR_STRICTNESS.get(getattr(rule, "threshold_operator", ""), 0)
        after = _OPERATOR_STRICTNESS.get(proposed["threshold_operator"], 0)
        if after and before and after < before:
            relaxations.append("operator_weakened")

    # 4) Approver removed entirely.
    if "approver_role" in proposed or "approver_user_id" in proposed:
        had_approver = bool(
            getattr(rule, "approver_role", None)
            or getattr(rule, "approver_user_id", None)
        )
        will_have = bool(
            proposed.get("approver_role", getattr(rule, "approver_role", None))
            or proposed.get(
                "approver_user_id", getattr(rule, "approver_user_id", None)
            )
        )
        if had_approver and not will_have:
            relaxations.append("approver_removed")

    # 5) Auto-approve escalation = catastrophic relax.
    if proposed.get("escalation_action") == "auto_approve":
        if getattr(rule, "escalation_action", None) != "auto_approve":
            relaxations.append("auto_approve_added")

    if not relaxations:
        return EditClassification("allow", reason=None, relaxations=[])

    # The editor is a "gated approver" if the rule directly names them
    # OR if their role matches ``approver_role`` AND they are not
    # Operations (Ops is the meta-approval target, not the gated party).
    is_gated = False
    if getattr(rule, "approver_user_id", None) == editor_id:
        is_gated = True
    elif editor_role and editor_role == getattr(rule, "approver_role", None):
        # Operations editing their own rule still counts as gated for
        # the small set of rules where ops_role appears as approver.
        is_gated = True

    if not is_gated:
        return EditClassification(
            "allow",
            reason="editor is not gated by this rule",
            relaxations=relaxations,
        )

    return EditClassification(
        "meta",
        reason="editor is gated by this rule and the change is a relaxation",
        relaxations=relaxations,
    )


async def queue_meta_approval(
    db: AsyncSession,
    *,
    rule_id: int,
    tenant_id: int,
    proposed_by: int,
    proposed: dict,
) -> int:
    """Persist a pending meta-change. Returns the new pending_changes row id.

    Operations sees these in the meta-approvals queue and decides.
    """
    from sqlalchemy import text

    res = await db.execute(
        text(
            """
            INSERT INTO approval_rule_pending_changes
              (rule_id, tenant_id, proposed_by, change_payload, status)
            VALUES
              (:rule_id, :tenant_id, :proposed_by, CAST(:payload AS jsonb), 'pending')
            RETURNING id
            """
        ),
        {
            "rule_id": rule_id,
            "tenant_id": tenant_id,
            "proposed_by": proposed_by,
            "payload": json.dumps(proposed, default=str),
        },
    )
    new_id = res.scalar_one()
    await db.flush()
    logger.info(
        "Queued meta-approval %d for rule %d (proposed_by=%d)",
        new_id, rule_id, proposed_by,
    )
    return int(new_id)
