"""Round-5 R5-FLAG-17 — feature-flag symmetry between SPA and backend.

Pre-R5 a flag could appear in ``_PUBLIC_FEATURE_FLAGS`` (so the SPA
wraps a route in ``<FeatureFlagGate>``) without any backend check
gating the corresponding API. A token holder could then bypass the
SPA gate by calling the API directly.

This test enforces the invariant: every flag the SPA can read must
either (a) gate at least one backend router or (b) be explicitly
allow-listed below as service-internal-only.

Run as part of the regular suite — fast, file-grep only, no DB.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.api.v1.config import _PUBLIC_FEATURE_FLAGS


# Flags that are exposed to the SPA but legitimately have no backend
# router gate — typically because they control service-layer behaviour
# (event emission, caching, computation) that the SPA only references
# for tooltip text or copy variation.
_SERVICE_INTERNAL_FLAGS: set[str] = {
    # FEATURE_INVOICE_PAID_EVENT — gates event_bus.publish in the
    # invoice mark-paid handler; SPA reads to render an "auto-rollup
    # enabled" hint near the CTA.
    "FEATURE_INVOICE_PAID_EVENT",
    # FEATURE_AI_SUMMARIES / PIPELINE_SUGGESTIONS / TRIAGE / DEAL_RISK /
    # COMPETITIVE_INTEL / PREDICTIONS — these guard AI behaviours
    # inside service classes; SPA reads to show / hide the AI
    # affordances. Backend AI routes are gated by ai.py's
    # _require_* internally.
    "FEATURE_AI_SUMMARIES",
    "FEATURE_AI_PIPELINE_SUGGESTIONS",
    "FEATURE_AI_TRIAGE",
    "FEATURE_AI_DEAL_RISK",
    "FEATURE_AI_COMPETITIVE_INTEL",
    "FEATURE_AI_PREDICTIONS",
    # PWA / SESSION_MANAGEMENT — frontend-only chrome.
    "FEATURE_PWA",
    "FEATURE_SESSION_MANAGEMENT",
    # GUIDED_SELLING flag is read inside the wizard service; the
    # router gate is ai.py:_require_*. Both layers cooperate.
    "FEATURE_GUIDED_SELLING",
    # WEBHOOKS — gates outbound delivery; webhook config router is
    # always live.
    "FEATURE_WEBHOOKS",
    # BEHAVIORAL_SCORING — gates the event-bus subscriber that updates
    # lead scores in main.py:374 + workflow_service:266. No router
    # gate because score reads are always allowed; only the writes
    # are flag-gated.
    "FEATURE_BEHAVIORAL_SCORING",
    # SEQUENCES_V2 — main.py:352 wires the sequence step-completed
    # subscriber under this flag; workflow_service:159 short-circuits
    # the engine when off. Router-level gate exists upstream
    # (engagement.py mount conditions in router.py).
    "FEATURE_SEQUENCES_V2",
    # V6_REALTIME — event_recompute_hooks.py:54 short-circuits the
    # hook subscribers; no API surface to gate.
    "FEATURE_V6_REALTIME",
    # V7_LLM_OBJECTION — objection_intelligence_service.py:409 +
    # objection_llm_detector.py:65 gate the Claude proxy; reads of
    # already-stored intel are always allowed.
    "FEATURE_V7_LLM_OBJECTION",
}


def _api_v1_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "app" / "api" / "v1"


def _backend_gates() -> set[str]:
    """Return the set of flag names referenced anywhere in api/v1/.

    Catches every reference shape used in the codebase:
    - ``settings.FEATURE_X`` (most common)
    - ``cfg.FEATURE_X`` (settings imported as cfg)
    - ``getattr(settings, "FEATURE_X", ...)`` (defensive guards)
    """
    found: set[str] = set()
    patterns = (
        re.compile(r"(?:settings|cfg)\.(FEATURE_[A-Z0-9_]+)"),
        re.compile(r"getattr\(\s*(?:settings|cfg)\s*,\s*[\"'](FEATURE_[A-Z0-9_]+)[\"']"),
    )
    for path in _api_v1_dir().glob("*.py"):
        text = path.read_text()
        for pattern in patterns:
            for m in pattern.finditer(text):
                found.add(m.group(1))
    return found


def test_every_public_flag_has_backend_gate() -> None:
    """R5-FLAG-17 — SPA-exposed flags must be enforceable server-side.

    Either the flag appears in a ``settings.FEATURE_*`` reference in
    ``backend/app/api/v1/`` (gating at least one router) OR it's in
    the explicit allow-list above with a justification.
    """
    backend_refs = _backend_gates()
    missing = {
        flag
        for flag in _PUBLIC_FEATURE_FLAGS
        if flag not in backend_refs and flag not in _SERVICE_INTERNAL_FLAGS
    }
    assert not missing, (
        f"{len(missing)} flag(s) exposed to SPA but ungated in backend "
        f"api/v1/: {sorted(missing)}. Either add a "
        f"settings.{{name}} check in the corresponding router or move "
        f"the flag into _SERVICE_INTERNAL_FLAGS in this test with a "
        f"justification."
    )


def test_allow_list_entries_actually_exist() -> None:
    """Sanity: a flag in _SERVICE_INTERNAL_FLAGS that no longer exists
    in _PUBLIC_FEATURE_FLAGS is dead config — flag it so the next
    cleanup sweep removes it."""
    stale = _SERVICE_INTERNAL_FLAGS - _PUBLIC_FEATURE_FLAGS
    assert not stale, (
        f"Allow-list contains flags that aren't public anymore: "
        f"{sorted(stale)}. Remove from _SERVICE_INTERNAL_FLAGS."
    )
