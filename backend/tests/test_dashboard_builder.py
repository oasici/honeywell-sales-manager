"""Tests for dashboard builder API."""

from __future__ import annotations

import json

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.dashboard_config import DashboardConfig


@pytest.fixture(autouse=True)
def enable_dashboard_feature():
    original = settings.FEATURE_DASHBOARD_BUILDER
    settings.FEATURE_DASHBOARD_BUILDER = True
    yield
    settings.FEATURE_DASHBOARD_BUILDER = original


SAMPLE_WIDGETS = json.dumps([
    {"type": "chart", "report_id": 1, "position": {"x": 0, "y": 0, "w": 6, "h": 4}},
    {"type": "table", "report_id": 2, "position": {"x": 6, "y": 0, "w": 6, "h": 4}},
])


@pytest.mark.asyncio
async def test_create_dashboard(client: AsyncClient, auth_headers: dict):
    """Should create a new dashboard."""
    response = await client.post(
        "/api/v1/dashboards/",
        json={"name": "Test Dashboard", "widgets_json": SAMPLE_WIDGETS},
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == "Test Dashboard"
    assert data["id"] is not None


@pytest.mark.asyncio
async def test_list_dashboards(client: AsyncClient, auth_headers: dict):
    """Should list user's dashboards."""
    # Create one first
    await client.post(
        "/api/v1/dashboards/",
        json={"name": "List Test", "widgets_json": SAMPLE_WIDGETS},
        headers=auth_headers,
    )

    response = await client.get("/api/v1/dashboards/", headers=auth_headers)
    assert response.status_code == 200
    # Round-13 Sprint 7b — list endpoint now ships the canonical
    # PaginatedResponse envelope; legacy ``data`` alias dropped.
    items = response.json()["items"]
    assert len(items) >= 1


@pytest.mark.asyncio
async def test_update_dashboard(client: AsyncClient, auth_headers: dict):
    """Should update dashboard name and widgets."""
    create_resp = await client.post(
        "/api/v1/dashboards/",
        json={"name": "Original", "widgets_json": SAMPLE_WIDGETS},
        headers=auth_headers,
    )
    dashboard_id = create_resp.json()["data"]["id"]

    new_widgets = json.dumps([
        {"type": "kpi", "report_id": 3, "position": {"x": 0, "y": 0, "w": 12, "h": 2}},
    ])
    response = await client.put(
        f"/api/v1/dashboards/{dashboard_id}",
        json={"name": "Updated", "widgets_json": new_widgets},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Updated"


@pytest.mark.asyncio
async def test_delete_dashboard(client: AsyncClient, auth_headers: dict):
    """Should delete a dashboard."""
    create_resp = await client.post(
        "/api/v1/dashboards/",
        json={"name": "To Delete", "widgets_json": SAMPLE_WIDGETS},
        headers=auth_headers,
    )
    dashboard_id = create_resp.json()["data"]["id"]

    response = await client.delete(
        f"/api/v1/dashboards/{dashboard_id}",
        headers=auth_headers,
    )
    assert response.status_code == 204
