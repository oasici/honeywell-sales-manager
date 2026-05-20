"""Response schemas for the remaining ``PaginatedResponse[dict]`` holdouts
identified by the Round-15 cross-layer audit (``docs/audits/2026-05-20-
cross-layer-audit-round15.md`` §3.3 / Sprint 16h).

Each class mirrors the dict shape emitted by the corresponding handler's
``_serialize_*`` / ``_*_to_dict`` helper exactly. ``extra="allow"`` is
used where the handler enriches the row with caller-specific extras
(``user`` joins, computed fields) and the wire contract can't lock the
extra keys down without churning the SPA.

Schemas live in a single file because each is small (5-15 fields) and
binding them to ``backend/app/schemas/<entity>.py`` would dilute the
file boundary already established by Round-15 Sprint 16h cohort 1.
Future rounds may extract them per-entity if the namespace grows.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ── approvals ─────────────────────────────────────────────────────


class ApprovalRuleResponseRow(BaseModel):
    id: int
    tenant_id: int | None = None
    name: str | None = None
    entity_type: str | None = None
    condition_type: str | None = None
    threshold_value: float | None = None
    threshold_operator: str | None = None
    approver_role: str | None = None
    approver_user_id: int | None = None
    priority: int | None = None
    is_active: bool | None = None
    escalation_hours: int | None = None
    escalation_action: str | None = None
    chain_mode: str | None = None
    delegate_to: int | None = None
    delegate_until: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class ApprovalRequestRow(BaseModel):
    id: int
    entity_type: str | None = None
    entity_id: int | None = None
    rule_id: int | None = None
    level: int | None = None
    status: str | None = None
    requested_by: int | None = None
    assigned_to: int | None = None
    decided_by: int | None = None
    decided_at: str | None = None
    comments: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── audit ─────────────────────────────────────────────────────────


class AuditLogRow(BaseModel):
    id: int
    user_id: int | None = None
    tenant_id: int | None = None
    action: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    changes: str | None = None
    ip_address: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── users ─────────────────────────────────────────────────────────


class UserRow(BaseModel):
    """Public-safe user fields (no password hash, no secrets).

    Mirrors ``api/v1/users.py::_user_to_dict``. ``role`` is open-string
    so future role additions don't require a schema migration.
    """

    id: int
    tenant_id: int | None = None
    manager_id: int | None = None
    email: str | None = None
    full_name: str | None = None
    role: str | None = None
    is_active: bool | None = None
    email_setup_completed: bool | None = None
    password_change_required: bool | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── comments ──────────────────────────────────────────────────────


class CommentUserSummary(BaseModel):
    id: int
    full_name: str | None = None

    model_config = {"from_attributes": True}


class CommentRow(BaseModel):
    id: int
    tenant_id: int | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    user_id: int | None = None
    body: str | None = None
    mentions_json: str | None = None
    parent_id: int | None = None
    created_at: str | None = None
    updated_at: str | None = None
    user: CommentUserSummary | None = None
    # Nested replies — recursive list of the same shape. Typed as
    # ``list[dict]`` to avoid a circular reference; the SPA already
    # treats replies as the same shape as the parent.
    replies: list[dict[str, Any]] = []

    model_config = {"from_attributes": True, "extra": "allow"}


# ── custom_fields ─────────────────────────────────────────────────


class CustomFieldDefinitionRow(BaseModel):
    id: int
    tenant_id: int | None = None
    entity_type: str | None = None
    field_name: str | None = None
    field_label: str | None = None
    field_type: str | None = None
    is_required: bool | None = None
    options_json: str | None = None
    default_value: str | None = None
    help_text: str | None = None
    sort_order: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── leaderboard ───────────────────────────────────────────────────


class LeaderboardEntry(BaseModel):
    user_id: int
    full_name: str | None = None
    score: float | None = None
    rank: int | None = None
    deals_won: int | None = None
    revenue: float | None = None
    win_rate: float | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class AchievementRow(BaseModel):
    id: int
    tenant_id: int | None = None
    user_id: int | None = None
    achievement_type: str | None = None
    title: str | None = None
    description: str | None = None
    icon: str | None = None
    earned_at: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── forecast ──────────────────────────────────────────────────────


class ForecastAdjustmentRow(BaseModel):
    id: int
    opportunity_id: int | None = None
    adjusted_by: int | None = None
    original_amount: float | None = None
    adjusted_amount: float | None = None
    original_category: str | None = None
    adjusted_category: str | None = None
    reason: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class ForecastSnapshotRow(BaseModel):
    id: int
    snapshot_date: str | None = None
    stage: str | None = None
    opportunity_count: int | None = None
    total_amount: float | None = None
    weighted_amount: float | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── revenue_recognition ────────────────────────────────────────────


class RevenueScheduleRow(BaseModel):
    id: int
    tenant_id: int | None = None
    contract_id: int | None = None
    recognition_type: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    total_amount: float | None = None
    recognized_amount: float | None = None
    currency: str | None = None
    created_by: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── pricing ────────────────────────────────────────────────────────


class PriceTierRow(BaseModel):
    id: int
    price_entry_id: int | None = None
    min_qty: int | None = None
    max_qty: int | None = None
    unit_price: float | None = None
    discount_pct: float | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── teams (sharing rules) ──────────────────────────────────────────


class SharingRuleRow(BaseModel):
    id: int
    tenant_id: int | None = None
    entity_type: str | None = None
    source_user_id: int | None = None
    target_user_id: int | None = None
    target_team_id: int | None = None
    permission_level: str | None = None
    is_active: bool | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── territories (list endpoint) ────────────────────────────────────


class TerritoryListRow(BaseModel):
    id: int
    tenant_id: int | None = None
    name: str | None = None
    parent_id: int | None = None
    manager_id: int | None = None
    is_active: bool | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── stakeholders ───────────────────────────────────────────────────


class StakeholderRow(BaseModel):
    id: int
    opportunity_id: int | None = None
    customer_id: int | None = None
    name: str | None = None
    email: str | None = None
    title: str | None = None
    phone: str | None = None
    seniority: str | None = None
    department_group: str | None = None
    buyer_role: str | None = None
    notes: str | None = None
    is_auto_detected: bool | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── deal_rooms ─────────────────────────────────────────────────────


class DealRoomRow(BaseModel):
    id: int
    opportunity_id: int | None = None
    name: str | None = None
    external_token: str | None = None
    shared_items_json: str | None = None
    mutual_action_plan_json: str | None = None
    welcome_message: str | None = None
    is_active: bool | None = None
    last_buyer_activity_at: str | None = None
    created_by: int | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── pipelines ──────────────────────────────────────────────────────


class PipelineRow(BaseModel):
    id: int
    tenant_id: int | None = None
    name: str | None = None
    description: str | None = None
    is_default: bool | None = None
    stage_config_json: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── product_rules ──────────────────────────────────────────────────


class ProductRuleRow(BaseModel):
    id: int
    spare_part_id: int | None = None
    category: str | None = None
    rule_type: str | None = None
    condition_json: Any | None = None
    action_json: Any | None = None
    priority: int | None = None
    is_active: bool | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── ai_attributes ──────────────────────────────────────────────────


class AiAttributeDefinitionRow(BaseModel):
    id: int
    tenant_id: int | None = None
    entity_type: str | None = None
    name: str | None = None
    description: str | None = None
    output_type: str | None = None
    is_active: bool | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class AiAttributeValueRow(BaseModel):
    id: int
    definition_id: int | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    value_json: str | None = None
    confidence: float | None = None
    computed_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── relationship_graph ─────────────────────────────────────────────


class RelationshipEdgeRow(BaseModel):
    id: int
    source_entity_type: str | None = None
    source_entity_id: int | None = None
    target_entity_type: str | None = None
    target_entity_id: int | None = None
    relationship_type: str | None = None
    weight: float | None = None
    metadata_json: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── network_intelligence ───────────────────────────────────────────


class NetworkSegmentRow(BaseModel):
    id: int | None = None
    name: str | None = None
    description: str | None = None
    metric: str | None = None
    cohort_size: int | None = None
    value: float | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class FederatedBenchmarkRow(BaseModel):
    cohort: str | None = None
    metric: str | None = None
    value: float | None = None
    percentile: float | None = None
    sample_size: int | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── admin_dead_letters ────────────────────────────────────────────


class DeadLetterEventRow(BaseModel):
    id: int
    event_type: str | None = None
    payload: Any | None = None
    error_message: str | None = None
    retry_count: int | None = None
    status: str | None = None
    created_at: str | None = None
    last_attempted_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── reports_v2 (folders + templates) ───────────────────────────────


class ReportFolderRow(BaseModel):
    id: int
    tenant_id: int | None = None
    name: str | None = None
    parent_id: int | None = None
    owner_id: int | None = None
    is_shared: bool | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


class ReportTemplateRow(BaseModel):
    id: int
    tenant_id: int | None = None
    name: str | None = None
    description: str | None = None
    entity_type: str | None = None
    config_json: str | None = None
    folder_id: int | None = None
    created_by: int | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── leads (scoring config) ─────────────────────────────────────────


class LeadScoringConfigRow(BaseModel):
    id: int
    tenant_id: int | None = None
    name: str | None = None
    weight: float | None = None
    is_active: bool | None = None
    rule_json: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── next_best_actions ──────────────────────────────────────────────


class NextBestActionRow(BaseModel):
    id: int | None = None
    opportunity_id: int | None = None
    action_type: str | None = None
    title: str | None = None
    description: str | None = None
    priority: str | None = None
    score: float | None = None
    metadata_json: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── guided_selling ─────────────────────────────────────────────────


class GuidedSellingRow(BaseModel):
    id: int | None = None
    stage: str | None = None
    title: str | None = None
    description: str | None = None
    required: bool | None = None
    completed: bool | None = None
    order: int | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── momentum ───────────────────────────────────────────────────────


class MomentumHistoryRow(BaseModel):
    id: int | None = None
    opportunity_id: int | None = None
    score: float | None = None
    delta: float | None = None
    factor: str | None = None
    reason: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── engagement (transcripts) ───────────────────────────────────────


class EngagementTranscriptRow(BaseModel):
    id: int
    tenant_id: int | None = None
    opportunity_id: int | None = None
    customer_id: int | None = None
    title: str | None = None
    transcript_text: str | None = None
    duration_minutes: int | None = None
    sentiment: str | None = None
    keyword_hits_json: str | None = None
    summary: str | None = None
    created_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}


# ── chat (auto-response rules) ─────────────────────────────────────


class ChatAutoResponseRuleRow(BaseModel):
    id: int
    tenant_id: int | None = None
    trigger_pattern: str | None = None
    response_text: str | None = None
    is_active: bool | None = None
    priority: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    model_config = {"from_attributes": True, "extra": "allow"}
