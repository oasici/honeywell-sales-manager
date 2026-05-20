"""Public-facing config endpoint.

Surfaces the subset of ``app.core.config.Settings`` the frontend
needs to drive UI gating: which feature flags are on, the env name,
and the build/release tag. Everything here is **non-sensitive** —
secrets, DB URLs, JWT keys, AI keys, etc. are intentionally NOT
exposed and never will be.

Frontend hook lives at ``frontend/src/contexts/FeatureFlagContext.tsx``;
without this endpoint the UI hard-coded routes that 404'd when their
backing feature flag was off, producing the generic "Beklenmeyen bir
hata" toast — the V13 audit's #5.4 finding.
"""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.config import FeatureFlagsResponse

router = APIRouter(prefix="/config", tags=["config"])


# Allow-list of FEATURE_* settings the frontend is allowed to read.
# Adding a new flag to this set is an explicit decision so we don't
# accidentally leak experimental flags via a wildcard.
#
# Sprint 16e A2 (Round-16 deferred-plan) — each flag is annotated with
# its verified-intent classification:
#
#   * ``# spa-gated``       — FE renders a ``<FeatureFlagGate>`` or
#                             ``isEnabled()`` check before showing UI;
#                             allowlist entry is load-bearing.
#   * ``# backend-only``    — backend gates the route via ``_require_*``;
#                             FE just calls the API and renders the
#                             response. Allowlist exposes the flag so
#                             the SPA *could* render an "off" panel, but
#                             nothing breaks if it doesn't.
#   * ``# admin-only``      — admin/ops surfaces that are role-gated; the
#                             flag tightens that further. Useful for
#                             ops/release toggles.
#   * ``# deferred-fe-gate``— a known audit finding (Round-15 N15-FLAG-X)
#                             — backend has the gate but the SPA still
#                             shows the affordance unconditionally. Wire
#                             a ``<FeatureFlagGate>`` in the follow-up.
_PUBLIC_FEATURE_FLAGS: set[str] = {
    "FEATURE_RAG",  # backend-only — /api/v1/rag/* index/search; SPA just calls API
    "FEATURE_V2_BOARD",  # spa-gated — wraps board routes in App.tsx
    "FEATURE_V4_FEATURE_STORE",  # backend-only — feature_store service internal
    "FEATURE_V4_ADDITIVE_READMODEL",  # backend-only — sales-events shadow read model
    "FEATURE_V4_SALES_EVENTS_SHADOW",  # backend-only — sales-events shadow writer
    "FEATURE_V4_DEAL_REPLAY",  # spa-gated — DealReplay panel route
    "FEATURE_V4_SALES_DNA",  # spa-gated — SalesDna page route
    "FEATURE_V5_INTELLIGENCE",  # spa-gated — intelligence routes
    "FEATURE_V6_REALTIME",  # backend-only — cockpit SSE infra
    "FEATURE_V7_LLM_OBJECTION",  # backend-only — LLM objection detection in scoring
    "FEATURE_V9_CRM_SYNC",  # spa-gated — CRM-sync admin page
    "FEATURE_V9_CALENDAR_OAUTH",  # spa-gated — Integrations page Google/Outlook tiles
    "FEATURE_V9_NL_SEARCH",  # spa-gated — NL search bar in chrome
    # R5-FLAG-18 — FEATURE_TRANSFORMER_SEQ_EMBEDDING is consumed only
    # inside deal_similarity_service; there's no SPA action gated on
    # it, so dropping from the public list reduces noise on the
    # frontend's flag-fetch response. Service still reads it from
    # settings directly.
    "FEATURE_V10_PARTS_INTEL",  # spa-gated — V10 parts-intel routes
    "FEATURE_TASKS",  # spa-gated — Tasks affordance in App.tsx
    "FEATURE_AI_SUMMARIES",  # backend-only — /ai/summarize endpoints; FE renders result inline
    "FEATURE_AI_PIPELINE_SUGGESTIONS",  # backend-only — /ai/suggest-pipeline-update; result rendered inline
    "FEATURE_BUYER_MAP",  # spa-gated — BuyerRelationshipMap wrapped in <FeatureFlagGate> on OpportunityDetailPage (Round-16 A2)
    # Round-4 R4-FLAG-1 — expose the 17 backend-gated features that
    # the frontend was unable to gate before. With these listed, the
    # SPA can render <FeatureFlagGate> properly instead of letting
    # users navigate to routes that 404 silently.
    "FEATURE_REVENUE_COCKPIT",  # spa-gated — Cockpit route
    "FEATURE_LEAD_LIFECYCLE",  # spa-gated — Lead module routes
    "FEATURE_APPROVAL_ROUTING",  # spa-gated — Approvals routes
    "FEATURE_DASHBOARD_BUILDER",  # spa-gated — Dashboard builder routes
    "FEATURE_REPORT_BUILDER",  # spa-gated — Reports routes
    "FEATURE_CUSTOM_FIELDS",  # spa-gated — admin custom-fields page
    "FEATURE_FIELD_PERMISSIONS",  # admin-only — field-permissions admin tool
    "FEATURE_PRODUCT_RULES",  # spa-gated — product-rules admin page
    "FEATURE_WORKFLOW_RULES",  # spa-gated — workflow-rules admin page
    "FEATURE_TERRITORIES",  # spa-gated — territories page
    "FEATURE_LIVE_CHAT",  # spa-gated — Chat routes
    "FEATURE_MULTI_PIPELINE",  # spa-gated — pipeline switcher UI
    "FEATURE_INVOICING",  # spa-gated — Invoicing routes
    # R5-FLAG-19 — FEATURE_INVOICE_PAID_EVENT drives the in-process
    # event_bus.publish('invoice.paid') side effect; expose so the SPA
    # can render an "auto-rollup enabled" hint near the mark-paid CTA.
    "FEATURE_INVOICE_PAID_EVENT",  # backend-only — event bus internal; allowlisted per R5-FLAG-19 hint rationale
    "FEATURE_CONTRACTS",  # spa-gated — Contracts routes (R5-FLAG-15)
    "FEATURE_SUBSCRIPTIONS",  # spa-gated — Subscriptions routes (R5-FLAG-15)
    "FEATURE_REV_REC",  # spa-gated — RevenueRecognition page
    "FEATURE_CAMPAIGNS",  # spa-gated — Campaigns routes
    "FEATURE_BREACH_WORKFLOW",  # spa-gated — Compliance routes (R4-FLAG-3)
    "FEATURE_DEAL_HEALTH",  # backend-only — deal_health_service; FE renders health badges on opps when present
    "FEATURE_GUIDED_SELLING",  # backend-only — stage_validation_service; FE renders stage warnings when present
    "FEATURE_AI_TRIAGE",  # backend-only — AI triage on email parsing; FE renders triage badges
    "FEATURE_AI_DEAL_RISK",  # backend-only — /ai/deal-risk; FE calls endpoint, renders result
    "FEATURE_AI_COMPETITIVE_INTEL",  # backend-only — /ai/competitive-intel; same pattern
    "FEATURE_AI_PREDICTIONS",  # backend-only — predict-close/predict-churn endpoints
    "FEATURE_TEAM_ACCESS",  # backend-only — Round-16 A2 sweep found no FE consumer; backend gates /teams/* endpoints
    "FEATURE_SESSION_MANAGEMENT",  # backend-only — Round-16 A2 sweep found no FE consumer; backend gates /auth/sessions/* endpoints
    "FEATURE_WEBHOOKS",  # spa-gated — SettingsPage wraps WebhookSettings in <FeatureFlagGate> (Round-16 A2)
    "FEATURE_PUBLIC_API",  # backend-only — Round-16 A2 sweep found no FE consumer; backend gates /api-keys endpoints
    "FEATURE_ESIGN",  # backend-only — signing service; FE renders signature affordance on quotes when present
    "FEATURE_SEQUENCES_V2",  # spa-gated — Sequences V2 routes
    "FEATURE_BEHAVIORAL_SCORING",  # backend-only — scoring_service internal
    "FEATURE_PWA",  # backend-only — PWA manifest endpoints; SPA serves manifest regardless
    # Round-8 plan-adoption flags. Allowlisted so the SPA's
    # ``<FeatureFlagGate>`` can read them — without this entry the
    # flag is omitted from the public response, ``isEnabled`` returns
    # ``Boolean(undefined) === false`` and the page surfaces the
    # generic "Bu özellik bu hesap için kapalı" panel even when the
    # backend has the feature on.
    "FEATURE_NETWORK_INTELLIGENCE",  # spa-gated — NetworkInsight page route
    "FEATURE_AI_ATTRIBUTES",  # spa-gated — admin AI-attributes page
    "FEATURE_DECISION_GRAPH",  # spa-gated — OpportunityDetailPage wraps DecisionGraphPanel in <FeatureFlagGate> (Round-16 A2)
}


@router.get("/feature-flags", response_model=FeatureFlagsResponse)
async def get_feature_flags(
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the live feature-flag state for the current deployment.

    Auth-gated so unauthenticated probes can't enumerate which
    sprints we're shipping. Auth-only is sufficient — no role check
    because the frontend needs this on every page (even sales_rep).
    """
    flags: dict[str, bool] = {}
    for name in _PUBLIC_FEATURE_FLAGS:
        if hasattr(settings, name):
            flags[name] = bool(getattr(settings, name))

    return {
        "env": settings.ENV,
        # The release identifier helps support correlate user-reported
        # issues with the running container; mirrors the value Sentry
        # tags every event with.
        "release": os.environ.get("SENTRY_RELEASE")
        or os.environ.get("RENDER_GIT_COMMIT")
        or "dev",
        "flags": flags,
    }
