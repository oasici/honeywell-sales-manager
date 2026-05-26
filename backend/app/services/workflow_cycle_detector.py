"""F-015 — Workflow rule cycle + depth detection.

Rules in ``app/models/workflow_rule.py`` can chain via field updates:
Rule A sets ``customer.tier='Platinum'`` → Rule B fires on
``customer.tier='Platinum'`` and sets ``customer.region='emea'`` →
Rule C fires on ``customer.region='emea'`` and sets ``tier='Gold'``
→ Rule A would refire on the tier change → ∞.

Pre-Round-19 the engine had no execution context; cycles spun until
PostgreSQL deadlocked or audit_log filled the disk. This module
adds a per-event context the rule engine threads through every
synchronous + asynchronous chain. Two guards:

  * **Depth cap** — at most ``MAX_DEPTH`` rules fire from a single
    root event. Beyond that, the engine raises
    :class:`WorkflowDepthExceeded` and writes a ``blocked_depth``
    row to ``workflow_execution_log``.
  * **Cycle visit** — the context tracks ``visited_rules``; the
    same rule cannot fire twice within one chain. Re-entry raises
    :class:`WorkflowCycleDetected` and logs ``blocked_cycle``.

The context is a value object — engines pass it by argument, never
mutate via thread-locals. Tests can construct it directly without
any DB.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Iterable

logger = logging.getLogger(__name__)


MAX_DEPTH = 5
"""Maximum number of rules a single root event may trigger.

Five rules is generous: it covers any realistic
"customer-update → notify-manager → assign-territory → set-tier →
re-score" pipeline a sales-ops team would build, while still
shutting down a runaway chain quickly enough that PostgreSQL never
sees the deadlock. Tunable per tenant once the abuse pattern is
better characterised."""


class WorkflowCycleDetected(Exception):
    """Raised when the same rule attempts to fire twice in one chain."""


class WorkflowDepthExceeded(Exception):
    """Raised when the chain depth exceeds :data:`MAX_DEPTH`."""


@dataclass
class RuleExecutionContext:
    """Per-event chain state.

    Construct one at the *root* event (the CRUD action that
    triggered the first rule). Pass it down through every fired
    rule. Each rule fire calls :meth:`enter` to register, then
    :meth:`exit_` after the fire (so a rule that recursively
    triggers itself directly is caught even mid-execution).
    """

    root_event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    depth: int = 0
    visited_rules: set[int] = field(default_factory=set)
    max_depth: int = MAX_DEPTH

    def enter(self, rule_id: int) -> None:
        """Register a rule about to fire. Raises if it would loop."""
        if self.depth >= self.max_depth:
            raise WorkflowDepthExceeded(
                f"workflow chain exceeded depth {self.max_depth} "
                f"(root_event={self.root_event_id})"
            )
        if rule_id in self.visited_rules:
            raise WorkflowCycleDetected(
                f"rule {rule_id} would re-fire in same chain "
                f"(root_event={self.root_event_id})"
            )
        self.visited_rules.add(rule_id)
        self.depth += 1

    def exit_(self, rule_id: int) -> None:
        """Pair with :meth:`enter`. Allows the next sibling rule to fire."""
        self.depth -= 1
        # NOTE: we deliberately do NOT remove from visited_rules.
        # Once a rule has fired in a chain it stays "visited" — that's
        # what blocks A→B→A cycles. ``depth`` is what we restore.

    def remaining_budget(self) -> int:
        return max(0, self.max_depth - self.depth)


def detect_static_cycles(
    rules: Iterable[object],
    *,
    rule_id_attr: str = "id",
    trigger_attr: str = "trigger_event",
    action_attr: str = "action_event",
) -> list[tuple[int, ...]]:
    """Static analysis of saved rules. Returns every cycle found.

    Builds an adjacency list ``action_event → [rules-triggering-on-it]``
    and walks each rule's downstream chain looking for self-revisit.
    Used at *save time* to refuse persistence of a rule that would
    introduce a cycle, so operators see the error before any event
    fires.

    Pure-function: takes any iterable of rule-like objects with the
    three named attributes. Returns the list of cycles as tuples of
    rule IDs in firing order. Empty list = graph is acyclic.
    """
    graph: dict[str, list[object]] = {}
    rule_by_id: dict[int, object] = {}
    for r in rules:
        rid = getattr(r, rule_id_attr, None)
        if rid is None:
            continue
        rule_by_id[rid] = r
        trig = getattr(r, trigger_attr, None)
        if trig:
            graph.setdefault(trig, []).append(r)

    cycles: list[tuple[int, ...]] = []

    def walk(start: object, path: list[int]) -> None:
        action = getattr(start, action_attr, None)
        if not action:
            return
        next_rules = graph.get(action, [])
        for nxt in next_rules:
            nxt_id = getattr(nxt, rule_id_attr, None)
            if nxt_id is None:
                continue
            if nxt_id in path:
                cycles.append(tuple(path + [nxt_id]))
                continue
            if len(path) >= MAX_DEPTH:
                continue
            walk(nxt, path + [nxt_id])

    for r in rule_by_id.values():
        rid = getattr(r, rule_id_attr, None)
        if rid is not None:
            walk(r, [rid])

    # Deduplicate (multiple paths can hit the same cycle).
    seen: set[frozenset[int]] = set()
    out: list[tuple[int, ...]] = []
    for c in cycles:
        key = frozenset(c)
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out
