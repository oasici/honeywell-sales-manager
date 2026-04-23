import pytest
from unittest.mock import patch


@pytest.mark.asyncio
async def test_ops_feature_flags_requires_auth(client):
    r = await client.get("/api/v1/ops/feature-flags")
    # get_current_user -> 401
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_ai_summarize_requires_role(client, db):
    # With flags on, still requires auth (401)
    with patch("app.api.v1.ai.settings") as m:
        m.FEATURE_AI_SUMMARIES = True
        r = await client.post("/api/v1/ai/summarize", json={"entity_type": "opportunity", "entity_id": 1})
        assert r.status_code == 401

