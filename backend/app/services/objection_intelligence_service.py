"""Objection Intelligence service (V5).

End-to-end objection lifecycle:

1. **Detection** — keyword + heuristic rules over event/email text.
   The richer NLP variant in ``conversation_insights_service`` may
   feed us via ``record_objection`` instead; this module is tolerant
   of both flows.

2. **Resolution tracking** — every action a rep takes after the
   objection (revised quote, ROI note, technical call, …) is
   recorded against the objection so we can compute time-to-resolve
   and success-by-action.

3. **Pattern mining** — for each ``(segment_key, objection_type)``
   pair, compute the action types that historically led to wins and
   publish them in ``objection_patterns``. The nightly job calls
   ``refresh_patterns()``.

This is the rule-based MVP — no LLM required. We log evidence text so a
later sprint can swap in an LLM detector without losing data.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.opportunity import Opportunity
from app.models.v5_objection import (
    Objection,
    ObjectionPattern,
    ObjectionResolutionAction,
)
from app.services.segment_key import derive_segment_key

logger = logging.getLogger(__name__)


# ─────────────────────── Objection taxonomy ──────────────────────────

OBJECTION_TYPES = (
    "price",
    "timing",
    "security",
    "integration",
    "authority",
    "priority",
    "procurement",
    "competition",
)

# Keyword → objection_type map used by the rule-based detector.
# Each entry is (lowercase keyword, type, base severity). Severity may be
# upgraded by the caller if context (e.g. negotiation stage) warrants.
_KEYWORD_RULES: tuple[tuple[str, str, str], ...] = (
    # price
    ("pahalı", "price", "med"),
    ("bütçe", "price", "med"),
    ("indirim", "price", "med"),
    ("expensive", "price", "med"),
    ("budget", "price", "med"),
    ("discount", "price", "med"),
    # timing
    ("şu an değil", "timing", "low"),
    ("ileride", "timing", "low"),
    ("not the right time", "timing", "med"),
    # security / legal
    ("güvenlik", "security", "high"),
    ("kvkk", "security", "high"),
    ("gdpr", "security", "high"),
    ("legal", "security", "high"),
    # integration
    ("entegrasyon", "integration", "med"),
    ("api", "integration", "low"),
    # authority
    ("yöneticime sormam", "authority", "med"),
    ("müdüre", "authority", "med"),
    ("decision maker", "authority", "med"),
    # priority
    ("öncelik", "priority", "low"),
    ("not a priority", "priority", "med"),
    # procurement
    ("satınalma", "procurement", "med"),
    ("procurement", "procurement", "med"),
    # competition
    ("rakip", "competition", "high"),
    ("competitor", "competition", "high"),
)


@dataclass(frozen=True)
class DetectedObjection:
    """In-memory shape returned by ``detect_objections``."""

    objection_type: str
    severity: str
    evidence_text: str


# ─────────────────────── Detection (rule MVP) ────────────────────────


def detect_in_text(text: str | None) -> list[DetectedObjection]:
    """Return all objections found in ``text``. Empty list if no signal.

    Multiple objection types can be detected per call. Duplicate types
    keep the first-matched evidence to make downstream dedupe easy.
    """
    if not text:
        return []
    haystack = text.lower()
    seen: dict[str, DetectedObjection] = {}
    for keyword, otype, severity in _KEYWORD_RULES:
        if keyword in haystack and otype not in seen:
            # Keep a 240-char window around the keyword as evidence.
            idx = haystack.find(keyword)
            start = max(0, idx - 80)
            end = min(len(text), idx + len(keyword) + 80)
            seen[otype] = DetectedObjection(
                objection_type=otype,
                severity=severity,
                evidence_text=text[start:end].strip(),
            )
    return list(seen.values())


# ─────────────────────── Persistence helpers ─────────────────────────


async def record_objection(
    db: AsyncSession,
    *,
    opportunity_id: int,
    detection: DetectedObjection,
    event_id: int | None = None,
) -> Objection:
    """Persist a detected objection. Idempotent on (opp, type, evidence)."""
    # Cheap dedupe — same opp+type+text unresolved → return the existing.
    existing = (
        await db.execute(
            select(Objection)
            .where(Objection.opportunity_id == opportunity_id)
            .where(Objection.objection_type == detection.objection_type)
            .where(Objection.resolved_flag.is_(False))
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    obj = Objection(
        opportunity_id=opportunity_id,
        event_id=event_id,
        objection_type=detection.objection_type,
        severity=detection.severity,
        evidence_text=detection.evidence_text,
    )
    db.add(obj)
    await db.flush()
    return obj


async def record_resolution_action(
    db: AsyncSession,
    *,
    objection_id: int,
    action_type: str,
    payload: dict | None = None,
    mark_resolved: bool = False,
) -> ObjectionResolutionAction:
    """Append a resolution action and optionally close the objection.

    ``mark_resolved`` should only be set when the rep explicitly says
    "this is resolved" — otherwise we leave it open and let the
    pattern miner aggregate by *all* actions taken.
    """
    action = ObjectionResolutionAction(
        objection_id=objection_id,
        action_type=action_type,
        payload_json=json.dumps(payload) if payload else None,
    )
    db.add(action)

    if mark_resolved:
        obj = await db.get(Objection, objection_id)
        if obj is not None and not obj.resolved_flag:
            now = datetime.now(timezone.utc)
            obj.resolved_flag = True
            obj.resolved_at = now
            if obj.created_at is not None:
                delta = now - obj.created_at
                obj.ttr_hours = round(delta.total_seconds() / 3600.0, 2)

    await db.flush()
    return action


# ─────────────────────── Pattern mining ──────────────────────────────


async def refresh_patterns(db: AsyncSession) -> int:
    """Recompute ``objection_patterns`` rows from historical objections.

    Strategy:
      1. Pull all objections joined to their opportunity (for segment).
      2. Group by (segment_key, objection_type).
      3. For each group, compute the share of resolved+won outcomes
         per action_type and pick the top 3 as the recommendation.

    Returns the number of (segment, objection_type) rows upserted.
    """
    # Pull denormalized rows. We keep the whole join in memory because
    # cardinality is small relative to a manager's deal book; switch to
    # set-based SQL if this grows past ~100k objections.
    rows = (
        await db.execute(
            select(Objection, Opportunity).join(
                Opportunity, Objection.opportunity_id == Opportunity.id
            )
        )
    ).all()

    # group_key → list of (objection, opportunity, [action_types])
    groups: dict[tuple[str, str], list[tuple[Objection, Opportunity, list[str]]]] = {}
    for obj, opp in rows:
        seg = derive_segment_key(
            industry=getattr(opp, "industry", None),
            employee_count=getattr(opp, "employee_count", None),
            amount_try=opp.amount,
            product_family=getattr(opp, "product_family", None),
        )
        action_rows = (
            await db.execute(
                select(ObjectionResolutionAction.action_type).where(
                    ObjectionResolutionAction.objection_id == obj.id
                )
            )
        ).scalars().all()
        groups.setdefault((seg, obj.objection_type), []).append(
            (obj, opp, list(action_rows))
        )

    upserts = 0
    for (segment_key, objection_type), entries in groups.items():
        action_success: dict[str, list[bool]] = {}
        for obj, opp, actions in entries:
            won = str(getattr(opp, "stage", "")) == "closed_won"
            for action_type in actions:
                action_success.setdefault(action_type, []).append(bool(won))

        if not action_success:
            continue

        ranked = sorted(
            (
                (
                    action_type,
                    sum(outcomes) / len(outcomes) if outcomes else 0.0,
                    len(outcomes),
                )
                for action_type, outcomes in action_success.items()
            ),
            key=lambda x: (-x[1], -x[2]),
        )[:3]

        recommendation = [
            {"action_type": at, "win_rate": round(rate, 3), "support": n}
            for at, rate, n in ranked
        ]
        sample_size = sum(n for _, _, n in ranked)
        success_rate = (
            sum(rate * n for _, rate, n in ranked) / sample_size
            if sample_size
            else 0.0
        )

        # Upsert by unique (segment_key, objection_type)
        existing = (
            await db.execute(
                select(ObjectionPattern)
                .where(ObjectionPattern.segment_key == segment_key)
                .where(ObjectionPattern.objection_type == objection_type)
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                ObjectionPattern(
                    segment_key=segment_key,
                    objection_type=objection_type,
                    recommended_resolution_json=json.dumps(recommendation),
                    success_rate=round(success_rate, 3),
                    sample_size=sample_size,
                )
            )
        else:
            existing.recommended_resolution_json = json.dumps(recommendation)
            existing.success_rate = round(success_rate, 3)
            existing.sample_size = sample_size
            existing.last_trained_at = datetime.now(timezone.utc)
        upserts += 1

    await db.flush()
    return upserts


async def suggest_resolution(
    db: AsyncSession,
    *,
    objection_id: int,
) -> list[dict]:
    """Top-3 recommended resolution actions for this objection.

    Returns ``[]`` when the segment hasn't been mined yet — caller
    decides whether to fall back to a generic playbook.
    """
    obj = await db.get(Objection, objection_id)
    if obj is None:
        return []
    opp = await db.get(Opportunity, obj.opportunity_id)
    if opp is None:
        return []
    seg = derive_segment_key(
        industry=getattr(opp, "industry", None),
        employee_count=getattr(opp, "employee_count", None),
        amount_try=opp.amount,
        product_family=getattr(opp, "product_family", None),
    )
    pattern = (
        await db.execute(
            select(ObjectionPattern)
            .where(ObjectionPattern.segment_key == seg)
            .where(ObjectionPattern.objection_type == obj.objection_type)
        )
    ).scalar_one_or_none()
    if pattern is None or not pattern.recommended_resolution_json:
        return []
    try:
        return list(json.loads(pattern.recommended_resolution_json))
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "Malformed objection_patterns.recommended_resolution_json for id=%s",
            pattern.id,
        )
        return []


# ─────────────────────── Convenience entry points ────────────────────


async def detect_and_record(
    db: AsyncSession,
    *,
    opportunity_id: int,
    text: str,
    event_id: int | None = None,
) -> list[Objection]:
    """One-shot helper for callers that don't need fine-grained control."""
    detections: Iterable[DetectedObjection] = detect_in_text(text)
    out: list[Objection] = []
    for d in detections:
        out.append(
            await record_objection(
                db,
                opportunity_id=opportunity_id,
                detection=d,
                event_id=event_id,
            )
        )
    return out
