from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.intelligence.additive.schemas import CanonicalSalesEvent, ConversationSignalView
from app.models.activity_log import ActivityLog
from app.models.opportunity import OpportunityEvent, OpportunitySignal
from app.models.revenue_signal import RevenueSignal


def _parse_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {"_raw": out}
    except json.JSONDecodeError:
        return {"_unparsed": raw}


def _infer_channel_from_activity(log: ActivityLog) -> str:
    et = (log.entity_type or "").lower()
    if et in ("email",):
        return "email"
    if et in ("quote",):
        return "quote"
    if et in ("task",):
        return "task"
    if et in ("transcript",):
        return "call"
    return "other"


def _infer_direction_from_activity(activity_type: str) -> str:
    t = (activity_type or "").lower()
    if "received" in t or "inbound" in t:
        return "inbound"
    if "sent" in t or "outbound" in t or "created" in t or "approved" in t:
        return "outbound"
    if "system" in t or "parsed" in t:
        return "system"
    return "internal"


def activity_log_to_canonical(log: ActivityLog, *, account_id: int | None) -> CanonicalSalesEvent:
    ts = log.created_at or datetime.now(timezone.utc)
    channel = _infer_channel_from_activity(log)
    direction = _infer_direction_from_activity(log.activity_type)
    actor_type = "rep" if log.user_id else "system"
    payload: dict[str, Any] = {
        "summary": log.summary,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "duration_minutes": log.duration_minutes,
        "outcome": log.outcome,
        "attendees_json": log.attendees_json,
        "agenda": log.agenda,
        **_parse_metadata(log.metadata_json),
    }
    return CanonicalSalesEvent(
        synthetic_id=f"activity_logs:{log.id}",
        provenance="activity_logs",
        account_id=account_id,
        opportunity_id=log.opportunity_id,
        contact_id=None,
        event_type=log.activity_type,
        event_ts=ts.isoformat(),
        actor_type=actor_type,
        actor_id=log.user_id,
        channel=channel,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        payload_json=payload,
        source_ref=log.source_ref or f"activity_log:{log.id}",
    )


def _channel_for_opportunity_event(event_type: str) -> str:
    t = (event_type or "").lower()
    if t in ("email",):
        return "email"
    if t in ("quote",):
        return "quote"
    if t in ("call",):
        return "call"
    if t in ("meeting",):
        return "meeting"
    if t in ("task",):
        return "task"
    if t in ("note",):
        return "other"
    if t in ("stage_change",):
        return "system"
    return "other"


def opportunity_event_to_canonical(ev: OpportunityEvent, *, account_id: int | None) -> CanonicalSalesEvent:
    ts = ev.occurred_at or datetime.now(timezone.utc)
    channel = _channel_for_opportunity_event(ev.event_type)
    direction = "internal" if channel in ("other", "system") else "outbound"
    payload: dict[str, Any] = {
        "description": ev.description,
        "entity_type": ev.entity_type,
        "entity_id": ev.entity_id,
    }
    return CanonicalSalesEvent(
        synthetic_id=f"opportunity_events:{ev.id}",
        provenance="opportunity_events",
        account_id=account_id,
        opportunity_id=ev.opportunity_id,
        contact_id=None,
        event_type=ev.event_type,
        event_ts=ts.isoformat(),
        actor_type="system",
        actor_id=None,
        channel=channel,  # type: ignore[arg-type]
        direction=direction,  # type: ignore[arg-type]
        payload_json=payload,
        source_ref=f"opportunity_event:{ev.id}",
    )


def merge_canonical_timeline(events: list[CanonicalSalesEvent]) -> list[CanonicalSalesEvent]:
    return sorted(events, key=lambda e: e.event_ts)


def _evidence_from_metadata(meta: dict[str, Any], recommended: str | None) -> str | None:
    raw = meta.get("raw")
    if isinstance(raw, dict):
        t = raw.get("snippet") or raw.get("text") or raw.get("message")
        if isinstance(t, str) and t.strip():
            return t[:2000]
    v = meta.get("value")
    if isinstance(v, str) and v.strip():
        return v[:2000]
    if recommended and recommended.strip():
        return recommended.strip()[:2000]
    return None


def _model_version_from_metadata(meta: dict[str, Any]) -> str | None:
    mv = meta.get("model_version")
    return str(mv) if mv is not None else None


def revenue_signal_to_conversation_view(rs: RevenueSignal) -> ConversationSignalView:
    meta = _parse_metadata(rs.metadata_json)
    evidence = _evidence_from_metadata(meta, rs.recommended_action)
    return ConversationSignalView(
        feed="revenue_signals",
        synthetic_id=f"revenue_signals:{rs.id}",
        opportunity_id=rs.opportunity_id,
        account_id=rs.customer_id,
        signal_type=rs.signal_type,
        signal_strength=rs.severity,
        confidence=float(rs.confidence or 0.0),
        evidence_text=evidence,
        model_version=_model_version_from_metadata(meta),
        event_key=rs.event_key,
        created_at=(rs.created_at or datetime.now(timezone.utc)).isoformat(),
        metadata=meta,
    )


def revenue_signal_to_canonical(rs: RevenueSignal) -> CanonicalSalesEvent:
    """Fold canonical signal stream into the same timeline as sales-like events."""
    meta = _parse_metadata(rs.metadata_json)
    ts = rs.created_at or datetime.now(timezone.utc)
    actor_type = "rep" if rs.owner_id else "system"
    payload: dict[str, Any] = {
        "signal_type": rs.signal_type,
        "severity": rs.severity,
        "confidence": rs.confidence,
        "recommended_action": rs.recommended_action,
        "source_entity_type": rs.source_entity_type,
        "source_entity_id": rs.source_entity_id,
        "is_resolved": rs.is_resolved,
        "depth": rs.depth,
        **meta,
    }
    return CanonicalSalesEvent(
        synthetic_id=f"revenue_signals:{rs.id}",
        provenance="revenue_signals",
        account_id=rs.customer_id,
        opportunity_id=rs.opportunity_id,
        contact_id=None,
        event_type=f"signal:{rs.signal_type}",
        event_ts=ts.isoformat(),
        actor_type=actor_type,  # type: ignore[arg-type]
        actor_id=rs.owner_id,
        channel="system",
        direction="system",
        payload_json=payload,
        source_ref=rs.event_key or f"revenue_signal:{rs.id}",
    )


def opportunity_signal_to_conversation_view(
    sig: OpportunitySignal, *, account_id: int | None
) -> ConversationSignalView:
    meta: dict[str, Any] = {
        "source_type": sig.source_type,
        "source_id": sig.source_id,
        "is_resolved": sig.is_resolved,
    }
    return ConversationSignalView(
        feed="opportunity_signals",
        synthetic_id=f"opportunity_signals:{sig.id}",
        opportunity_id=sig.opportunity_id,
        account_id=account_id,
        signal_type=sig.signal_type,
        signal_strength=sig.severity,
        confidence=0.5,
        evidence_text=sig.evidence,
        model_version="legacy-opportunity-signals",
        event_key=f"legacy_opportunity_signal:{sig.id}",
        created_at=(sig.created_at or datetime.now(timezone.utc)).isoformat(),
        metadata={k: v for k, v in meta.items() if v is not None},
    )


def opportunity_signal_to_canonical(sig: OpportunitySignal, *, account_id: int | None) -> CanonicalSalesEvent:
    ts = sig.created_at or datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "signal_type": sig.signal_type,
        "severity": sig.severity,
        "evidence": sig.evidence,
        "source_type": sig.source_type,
        "source_id": sig.source_id,
        "is_resolved": sig.is_resolved,
    }
    return CanonicalSalesEvent(
        synthetic_id=f"opportunity_signals:{sig.id}",
        provenance="opportunity_signals",
        account_id=account_id,
        opportunity_id=sig.opportunity_id,
        contact_id=None,
        event_type=f"legacy_signal:{sig.signal_type}",
        event_ts=ts.isoformat(),
        actor_type="system",
        actor_id=None,
        channel="system",
        direction="system",
        payload_json=payload,
        source_ref=f"legacy_opportunity_signal:{sig.id}",
    )
