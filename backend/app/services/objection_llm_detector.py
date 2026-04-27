"""LLM-hybrid objection detection (V7).

The V5 keyword detector misses paraphrased objections in long-form
text (call transcripts, multi-paragraph emails). This module wraps
Claude with a structured prompt that returns objections in the same
``OBJECTION_TYPES`` taxonomy the keyword detector uses, so the
downstream pipeline (recording, pattern mining) is unaffected.

Used by ``objection_intelligence_service.detect_and_record_hybrid``;
gated by ``FEATURE_V7_LLM_OBJECTION`` so Claude cost stays opt-in.
"""

from __future__ import annotations

import logging

from app.core.circuit_breaker import CircuitOpenError
from app.core.claude_client import claude_messages_create
from app.core.config import settings
from app.services.llm_json import parse_claude_json
from app.services.objection_intelligence_service import (
    OBJECTION_TYPES,
    DetectedObjection,
)

logger = logging.getLogger(__name__)


_VALID_SEVERITIES = {"low", "med", "high"}


_SYSTEM_PROMPT = (
    "Sen bir B2B satış asistanısın. Verilen metinden müşteri "
    "itirazlarını çıkar. Sadece geçerli kategorileri kullan. "
    "Her itiraz için 240 karakteri aşmayan kanıt metni ekle."
)


def _build_user_prompt(text: str) -> str:
    types_str = ", ".join(OBJECTION_TYPES)
    return (
        f"Aşağıdaki metinden müşteri itirazlarını çıkar.\n"
        f"Geçerli objection_type değerleri: {types_str}\n"
        f'Geçerli severity değerleri: low, med, high\n\n'
        f"Yalnızca JSON döndür:\n"
        f'{{"objections": ['
        f'{{"objection_type": "...", "severity": "...", "evidence_text": "..."}}'
        f"]}}\n\n"
        f"Metin:\n---\n{text[:6000]}\n---"
    )


async def detect_with_llm(text: str | None) -> list[DetectedObjection]:
    """Run Claude over ``text``; return validated detections.

    Returns ``[]`` on:
    - empty input
    - feature flag off
    - Claude breaker open
    - parse failure / type validation failure
    - any unhandled exception (we never raise on this best-effort path)
    """
    if not text or not text.strip():
        return []
    if not getattr(settings, "FEATURE_V7_LLM_OBJECTION", False):
        return []
    if not settings.ANTHROPIC_API_KEY:
        return []

    try:
        response = await claude_messages_create(
            model=settings.AI_MODEL_NAME,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_prompt(text)}],
        )
    except CircuitOpenError as exc:
        logger.warning("LLM objection detect skipped — breaker open: %s", exc)
        return []
    except Exception as exc:
        logger.warning("LLM objection detect failed: %s", exc)
        return []

    body = response.content[0].text if response.content else None
    parsed = parse_claude_json(body)
    if parsed is None:
        return []

    raw_items = parsed.get("objections")
    if not isinstance(raw_items, list):
        return []

    out: list[DetectedObjection] = []
    seen_types: set[str] = set()
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        otype = str(item.get("objection_type", "")).strip().lower()
        severity = str(item.get("severity", "med")).strip().lower()
        evidence = str(item.get("evidence_text", "")).strip()[:240]

        if otype not in OBJECTION_TYPES:
            continue
        if otype in seen_types:
            continue
        if severity not in _VALID_SEVERITIES:
            severity = "med"
        if not evidence:
            continue

        seen_types.add(otype)
        out.append(
            DetectedObjection(
                objection_type=otype,
                severity=severity,
                evidence_text=evidence,
            )
        )

    return out
