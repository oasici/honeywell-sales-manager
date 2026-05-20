"""Pydantic response schemas for /api/v1/territories/* endpoints.

Round-15 typing pass — every JSON endpoint in
``api/v1/territories.py`` gets a typed ``response_model`` so OpenAPI
/ SDK codegen consumers stop seeing ``any`` payloads.

Schemas mirror the dict shapes emitted by ``_serialize_territory`` /
``_serialize_assignment`` + the bespoke detail / metrics responses.
``model_config = {"from_attributes": True, "extra": "allow"}`` keeps
the contract additive — caller-specific enrichments survive.
"""
from __future__ import annotations

from pydantic import BaseModel


class TerritoryItem(BaseModel):
    """Flat territory row — matches ``_serialize_territory``."""

    id: int
    tenant_id: int | None = None
    name: str | None = None
    parent_id: int | None = None
    description: str | None = None
    region: str | None = None
    rules_json: str | None = None
    created_by: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class TerritoryTreeNode(BaseModel):
    """Recursive tree node — used by /tree endpoint."""

    id: int
    name: str | None = None
    region: str | None = None
    description: str | None = None
    children: list[TerritoryTreeNode] = []

    model_config = {"from_attributes": True}


class TerritoryTreeResponse(BaseModel):
    """GET /territories/tree — nested territory hierarchy."""

    tree: list[TerritoryTreeNode]

    model_config = {"from_attributes": True}


class TerritoryAssignmentItem(BaseModel):
    """Single assignment row — matches ``_serialize_assignment`` + user info."""

    id: int
    territory_id: int
    user_id: int
    role: str
    created_at: str | None = None
    # GET /{id} adds {"full_name", "email"} nested under "user"
    user: dict[str, str | None] | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class TerritoryDetailResponse(BaseModel):
    """GET /territories/{id} — detail + assignments."""

    territory: TerritoryItem
    assignments: list[TerritoryAssignmentItem]

    model_config = {"from_attributes": True}


class TerritoryMetricsResponse(BaseModel):
    """GET /territories/{id}/metrics — lightweight KPIs."""

    territory_id: int
    customer_count: int
    opportunity_count: int
    active_pipeline_total: float
    currency: str

    model_config = {"from_attributes": True}


class TerritoryOpportunityItem(BaseModel):
    """Single opportunity row in territory drill-down."""

    id: int
    title: str | None = None
    stage: str | None = None
    amount: float | None = None
    currency: str | None = None
    status: str | None = None
    owner_id: int | None = None
    customer_id: int | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class TerritoryOpportunitiesResponse(BaseModel):
    """GET /territories/{id}/opportunities — opportunity drill-down."""

    items: list[TerritoryOpportunityItem]
    total: int

    model_config = {"from_attributes": True}


class AutoAssignResponse(BaseModel):
    """POST /territories/auto-assign — rule-based bulk assignment ack."""

    assigned: int
    checked: int

    model_config = {"from_attributes": True}


# Resolve self-referencing forward ref on TerritoryTreeNode (Pydantic v2).
TerritoryTreeNode.model_rebuild()
