"""High-level sequence tokenizer (V6).

The V5 DNA miner used raw event types (``meeting_logged``, ``quote_sent``,
…) as its pattern signature. That's noisy: two deals with very
different timing or causality produce the same token list. The V6
tokenizer reduces a chronological event stream to a small set of
*behavioural* tokens that encode causality and timing thresholds.

Tokens emitted (a deal can have multiple):

* ``buyer_replied_within_48h`` — reply ≤48h after the rep's last outbound
* ``meeting_before_quote`` — at least one ``meeting_*`` event predates the first ``quote_sent``
* ``decision_maker_added_before_discount`` — a stakeholder with
  decision-maker flag was added before any discount > 0 quote item
* ``3plus_stakeholders_engaged`` — ≥ 3 distinct stakeholders touched
* ``discount_under_15`` — latest quote discount ≤ 15%
* ``followup_within_24h_after_quote`` — outbound rep activity ≤ 24h after ``quote_sent``
* ``quote_revised_after_objection`` — a ``quote_sent`` event follows an
  objection logged within 7 days
* ``stage_progressed_within_7d`` — at least one ``stage_changed`` to a
  later stage within any 7-day rolling window

The miner consumes these instead of raw types — pattern lift goes up
because the tokens already encode the causality the model would
otherwise have to infer.

Pure functions; no DB access. The miner pulls events + opp metadata
and passes them in.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol


class _EventLike(Protocol):
    event_type: str
    event_ts: object  # datetime


# Token names exported as constants so callers can match without
# spelling the literal twice.
TOK_BUYER_REPLY_FAST = "buyer_replied_within_48h"
TOK_MEETING_BEFORE_QUOTE = "meeting_before_quote"
TOK_DM_BEFORE_DISCOUNT = "decision_maker_added_before_discount"
TOK_3PLUS_STAKEHOLDERS = "3plus_stakeholders_engaged"
TOK_DISCOUNT_LOW = "discount_under_15"
TOK_FOLLOWUP_AFTER_QUOTE = "followup_within_24h_after_quote"
TOK_QUOTE_REVISED_AFTER_OBJECTION = "quote_revised_after_objection"
TOK_STAGE_PROGRESSED_FAST = "stage_progressed_within_7d"


# Stage rank used for "stage_progressed" detection.
_STAGE_ORDER: tuple[str, ...] = (
    "prospecting",
    "qualified",
    "proposal",
    "negotiation",
    "closed_won",
    "closed_lost",
)


@dataclass(frozen=True)
class TokenizerContext:
    """Side-channel data the event stream alone can't tell us about."""

    stakeholder_count: int = 0
    decision_maker_count: int = 0
    latest_discount_pct: float | None = None
    has_decision_maker_added_before_discount: bool = False


def _stage_rank(stage: str | None) -> int:
    if stage is None:
        return -1
    try:
        return _STAGE_ORDER.index(stage)
    except ValueError:
        return -1


def tokenize(events: Iterable[_EventLike], ctx: TokenizerContext | None = None) -> list[str]:
    """Reduce ``events`` (chronological) to a list of behaviour tokens.

    Returns the tokens in stable rule order (not event order) so the
    miner sees a consistent signature even when raw events shuffle by
    a few seconds.
    """
    ctx = ctx or TokenizerContext()
    seen: set[str] = set()
    sorted_events = sorted(list(events), key=lambda e: e.event_ts)

    # ── 1. buyer_replied_within_48h ──
    last_outbound_ts = None
    for ev in sorted_events:
        if ev.event_type in {"email_sent", "call_logged"}:
            last_outbound_ts = ev.event_ts
            continue
        if (
            ev.event_type == "email_received"
            and last_outbound_ts is not None
            and ev.event_ts - last_outbound_ts <= timedelta(hours=48)
        ):
            seen.add(TOK_BUYER_REPLY_FAST)
            break

    # ── 2. meeting_before_quote ──
    first_quote_ts = next(
        (e.event_ts for e in sorted_events if e.event_type == "quote_sent"), None
    )
    if first_quote_ts is not None:
        if any(
            e.event_type in {"meeting_logged", "meeting_booked", "demo_completed"}
            and e.event_ts < first_quote_ts
            for e in sorted_events
        ):
            seen.add(TOK_MEETING_BEFORE_QUOTE)

    # ── 3. decision_maker_added_before_discount ──
    if ctx.has_decision_maker_added_before_discount:
        seen.add(TOK_DM_BEFORE_DISCOUNT)

    # ── 4. 3+ stakeholders engaged ──
    if ctx.stakeholder_count >= 3:
        seen.add(TOK_3PLUS_STAKEHOLDERS)

    # ── 5. discount_under_15 ──
    if ctx.latest_discount_pct is not None and ctx.latest_discount_pct <= 15.0:
        seen.add(TOK_DISCOUNT_LOW)

    # ── 6. followup_within_24h_after_quote ──
    for i, ev in enumerate(sorted_events):
        if ev.event_type != "quote_sent":
            continue
        for nxt in sorted_events[i + 1 :]:
            if nxt.event_type in {"email_sent", "call_logged", "meeting_logged"}:
                if nxt.event_ts - ev.event_ts <= timedelta(hours=24):
                    seen.add(TOK_FOLLOWUP_AFTER_QUOTE)
                break

    # ── 7. quote_revised_after_objection ──
    for i, ev in enumerate(sorted_events):
        if ev.event_type != "objection_logged":
            continue
        for nxt in sorted_events[i + 1 :]:
            if nxt.event_type == "quote_sent" and nxt.event_ts - ev.event_ts <= timedelta(days=7):
                seen.add(TOK_QUOTE_REVISED_AFTER_OBJECTION)
                break

    # ── 8. stage_progressed_within_7d ──
    stage_changes = [e for e in sorted_events if e.event_type == "stage_changed"]
    for i in range(len(stage_changes) - 1):
        prev = stage_changes[i]
        for nxt in stage_changes[i + 1 :]:
            if nxt.event_ts - prev.event_ts > timedelta(days=7):
                break
            prev_stage = (prev.payload_json or {}).get("to") if hasattr(prev, "payload_json") else None
            nxt_stage = (nxt.payload_json or {}).get("to") if hasattr(nxt, "payload_json") else None
            if _stage_rank(nxt_stage) > _stage_rank(prev_stage):
                seen.add(TOK_STAGE_PROGRESSED_FAST)
                break
        if TOK_STAGE_PROGRESSED_FAST in seen:
            break

    # Stable order — token strings are immutable so sorted() is fine.
    return sorted(seen)
