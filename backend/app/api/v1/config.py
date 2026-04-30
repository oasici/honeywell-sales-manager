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
from app.core.security import get_current_user
from app.models.user import User

router = APIRouter(prefix="/config", tags=["config"])


# Allow-list of FEATURE_* settings the frontend is allowed to read.
# Adding a new flag to this set is an explicit decision so we don't
# accidentally leak experimental flags via a wildcard.
_PUBLIC_FEATURE_FLAGS: set[str] = {
    "FEATURE_RAG",
    "FEATURE_V2_BOARD",
    "FEATURE_V4_FEATURE_STORE",
    "FEATURE_V4_ADDITIVE_READMODEL",
    "FEATURE_V4_SALES_EVENTS_SHADOW",
    "FEATURE_V4_DEAL_REPLAY",
    "FEATURE_V4_SALES_DNA",
    "FEATURE_V5_INTELLIGENCE",
    "FEATURE_V6_REALTIME",
    "FEATURE_V7_LLM_OBJECTION",
    "FEATURE_V9_CRM_SYNC",
    "FEATURE_V9_CALENDAR_OAUTH",
    "FEATURE_V9_NL_SEARCH",
    "FEATURE_TRANSFORMER_SEQ_EMBEDDING",
    "FEATURE_V10_PARTS_INTEL",
    "FEATURE_TASKS",
    "FEATURE_AI_SUMMARIES",
    "FEATURE_AI_PIPELINE_SUGGESTIONS",
    "FEATURE_BUYER_MAP",
    "FEATURE_INSIGHTS",
    "FEATURE_COCKPIT",
    "FEATURE_COMPLIANCE",
    "FEATURE_KVKK",
}


@router.get("/feature-flags")
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
