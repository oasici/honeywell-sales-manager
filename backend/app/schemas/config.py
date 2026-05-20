"""Pydantic schemas for the public ``/config/*`` endpoints.

Round-16 N15-API-7 — tightens ``response_model=dict`` on
``GET /config/feature-flags`` to a real schema so the SPA's
``FeatureFlagContext`` consumes a typed shape instead of a bare
``Record<string, unknown>``.

Compatibility note: additive. The runtime payload is unchanged; only
the OpenAPI contract becomes explicit.
"""

from __future__ import annotations

from pydantic import BaseModel


class FeatureFlagsResponse(BaseModel):
    """``GET /config/feature-flags`` — runtime flag snapshot.

    ``flags`` is a free-form ``dict[str, bool]`` because the set of
    flags evolves per sprint; locking each one as a Required field
    here would force a schema change on every flag flip. The
    consumer (``FeatureFlagContext``) treats unknown flag names as
    "off" so adding new flags is non-breaking for the SPA.
    """

    env: str
    release: str
    flags: dict[str, bool]

    model_config = {"from_attributes": True}
