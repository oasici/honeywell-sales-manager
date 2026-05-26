"""F-026 — quote version supersede logic.

When rep edits an already-sent (or accepted but not-yet-contracted)
quote, the system creates a new ``Quote`` row with ``version =
parent.version + 1`` rather than mutating the existing row. The old
row needs to be marked ``superseded_by_id = new.id`` so:

  * Re-sending the customer PDF for the old row is blocked.
  * Reports filter ``WHERE superseded_at IS NULL`` to count only
    the live version.
  * Customer-facing watermark / banner can label the stale PDF
    "SUPERSEDED — current version is v2".

The supersede write is a *small* transactional helper, but the
business rule it encodes is non-obvious enough that it deserves its
own file: future engineers grepping for "supersede" find the rule
+ the comments + the policy on accepted quotes (we *don't*
supersede an accepted quote — that's frozen for audit).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class QuoteSupersedeError(Exception):
    """Raised when supersede is attempted in a forbidden state."""


# Status set that's "safe to supersede".
# - draft   : never sent; just discard via update-in-place (no supersede needed)
# - sent    : customer has the PDF but hasn't decided yet → supersede with v2
# - declined: customer rejected → supersede if rep wants to revise
# - expired : auto-expired → supersede if rep wants to renew
_SUPERSEDABLE = {"sent", "declined", "expired"}

# Statuses we refuse to supersede.
# - accepted: legally binding once the customer accepted; v2 must be a
#             new quote ID, not a supersede.
# - cancelled: explicitly killed; no supersede.
_FROZEN = {"accepted", "cancelled"}


def can_supersede(parent_status: str) -> tuple[bool, str | None]:
    """Pure check. Returns (True, None) or (False, reason)."""
    if parent_status in _SUPERSEDABLE:
        return True, None
    if parent_status in _FROZEN:
        return False, f"parent_status_frozen:{parent_status}"
    if parent_status == "draft":
        return False, "draft_should_be_edited_in_place"
    return False, f"parent_status_unsupported:{parent_status}"


def mark_superseded(parent: Any, child: Any) -> None:
    """Mutate ``parent`` to point at ``child`` as its successor.

    Caller commits. No DB calls — pure attribute setting so tests can
    use plain objects.

    Raises ``QuoteSupersedeError`` when the parent's status forbids
    supersede.
    """
    ok, reason = can_supersede(getattr(parent, "status", ""))
    if not ok:
        raise QuoteSupersedeError(reason or "supersede_forbidden")

    parent.superseded_by_id = child.id
    parent.superseded_at = datetime.now(timezone.utc)
    # Status stays as-is — the customer's view of the parent doesn't
    # disappear, it just gains a "this has been replaced" badge.


def is_live(quote: Any) -> bool:
    """A quote is "live" when nothing has superseded it.

    Reports + dashboards filter by this. The legacy ``status`` field
    can't tell us this on its own (a v1 with status='sent' is still
    "sent" even when v2 exists).
    """
    return getattr(quote, "superseded_by_id", None) is None
