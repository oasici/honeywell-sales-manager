from app.models.enums import EmailStatus, QuoteStatus, ReviewStatus, UserRole
from app.models.user import User
from app.models.user_customer_pin import UserCustomerPin
from app.models.account_enrichment import AccountEnrichment
from app.models.customer import Customer
from app.models.email_request import EmailRequest
from app.models.spare_part import SparePart
from app.models.price_entry import PriceEntry
from app.models.quote import Quote
from app.models.quote_item import QuoteItem
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.setting import Setting
from app.models.ai_training_data import AITrainingData
from app.models.saved_view import SavedView
from app.models.opportunity import Opportunity, OpportunityEvent, OpportunitySignal, Task
from app.models.engagement import Transcript, KeywordPack, Sequence, SequenceEnrollment, Segment
from app.models.activity_log import ActivityLog
from app.models.lead import Lead
from app.models.approval import ApprovalRule, ApprovalRequest
from app.models.lead_scoring_config import LeadScoringConfig
from app.models.forecast import ForecastAdjustment, PipelineSnapshot
from app.models.forecast_snapshot_detail import ForecastSnapshotDetail
from app.models.webhook import WebhookSubscription, WebhookDelivery
from app.models.team import AccountTeam, SharingRule
from app.models.report import ReportTemplate
from app.models.revenue_signal import RevenueSignal
from app.models.playbook import Playbook, PlaybookExecution
from app.models.field_permission import FieldPermission
from app.models.user_session import UserSession
from app.models.product_rule import ProductRule
from app.models.lead_assignment_rule import LeadAssignmentRule
from app.models.feature_usage import FeatureUsage
from app.models.stage_requirement import StageRequirement
from app.models.competitor_mention import CompetitorMention
from app.models.feature_store_daily import AccountFeaturesDaily, OpportunityFeaturesDaily, RepFeaturesDaily
from app.models.buyer_state_history import BuyerStateHistory
from app.models.decision_gap import StakeholderRole, DecisionGap
from app.models.network_benchmarks import NetworkSegment, SegmentBenchmarksDaily
from app.models.sales_event_shadow import SalesEventShadow
from app.models.deal_replay_snapshot import DealReplaySnapshot
from app.models.sales_dna_snapshot import SalesDnaSnapshot
from app.models.action_experiment import ActionExperiment
from app.models.report_folder import ReportFolder
from app.models.dashboard_config import DashboardConfig
from app.models.retention_policy import RetentionPolicy
from app.models.breach_notification import BreachNotification
from app.models.coaching_plan import CoachingPlan
from app.models.coaching_snapshot import CoachingSnapshot
from app.models.api_key import ApiKey
from app.models.push_subscription import PushSubscription
from app.models.custom_field import CustomField, CustomFieldValue
from app.models.workflow_rule import WorkflowRule
from app.models.product_bundle import ProductBundle
from app.models.comment import Comment
from app.models.email_template import EmailTemplate
from app.models.stage_config import StageConfig
from app.models.achievement import Achievement
from app.models.deal_room import DealRoom
from app.models.shared_document import SharedDocument
from app.models.meeting_link import MeetingLink
from app.models.meeting_booking import MeetingBooking
from app.models.subscription import Subscription
from app.models.selling_guide import SellingGuide
from app.models.contract import Contract, ContractAmendment
from app.models.campaign import Campaign, CampaignMember
from app.models.invoice import Invoice
from app.models.signature import SignatureRequest
from app.models.pipeline import Pipeline
from app.models.territory import Territory, TerritoryAssignment
from app.models.pricing import PriceTier, CustomerPricing
from app.models.revenue_recognition import RevenueSchedule, RevenueScheduleEntry
from app.models.chat import ChatSession, ChatMessage, AutoResponseRule
from app.models.sequence_v2 import SequenceStepRun, DomainEvent, Stakeholder

# ── V5 intelligence platform ──
# See docs/v5-intelligence-plan.md. Imported here so SQLAlchemy
# registers their metadata before any migration runs.
from app.models.v5_foundation import Contact
from app.models.v5_objection import (
    Objection,
    ObjectionPattern,
    ObjectionResolutionAction,
)
from app.models.v5_timing import RecommendedActionWindow
from app.models.v5_dna_patterns import DnaPattern, DnaRecommendation
from app.models.v5_network import NetworkAnomaly, NetworkPattern
from app.models.v5_playbook import (
    PlaybookAdherence,
    PlaybookPerformance,
    PlaybookStep,
)
from app.models.v5_similarity import (
    DealSimilarityLink,
    OpportunityEmbedding,
    RepDnaProfile,
)

__all__ = [
    "EmailStatus",
    "QuoteStatus",
    "ReviewStatus",
    "UserRole",
    "User",
    "UserCustomerPin",
    "AccountEnrichment",
    "Customer",
    "EmailRequest",
    "SparePart",
    "PriceEntry",
    "Quote",
    "QuoteItem",
    "AuditLog",
    "Notification",
    "Setting",
    "AITrainingData",
    "SavedView",
    "Opportunity",
    "OpportunityEvent",
    "OpportunitySignal",
    "Task",
    "Transcript",
    "KeywordPack",
    "Sequence",
    "SequenceEnrollment",
    "Segment",
    "ActivityLog",
    "Lead",
    "ApprovalRule",
    "ApprovalRequest",
    "ForecastAdjustment",
    "PipelineSnapshot",
    "ForecastSnapshotDetail",
    "WebhookSubscription",
    "WebhookDelivery",
    "AccountTeam",
    "SharingRule",
    "ReportTemplate",
    "LeadScoringConfig",
    "RevenueSignal",
    "Playbook",
    "PlaybookExecution",
    "FieldPermission",
    "UserSession",
    "ProductRule",
    "LeadAssignmentRule",
    "FeatureUsage",
    "StageRequirement",
    "CompetitorMention",
    "OpportunityFeaturesDaily",
    "AccountFeaturesDaily",
    "RepFeaturesDaily",
    "BuyerStateHistory",
    "StakeholderRole",
    "DecisionGap",
    "NetworkSegment",
    "SegmentBenchmarksDaily",
    "SalesEventShadow",
    "DealReplaySnapshot",
    "SalesDnaSnapshot",
    "ActionExperiment",
    "ReportFolder",
    "DashboardConfig",
    "RetentionPolicy",
    "BreachNotification",
    "CoachingPlan",
    "CoachingSnapshot",
    "ApiKey",
    "PushSubscription",
    "CustomField",
    "CustomFieldValue",
    "WorkflowRule",
    "ProductBundle",
    "Comment",
    "EmailTemplate",
    "StageConfig",
    "Achievement",
    "DealRoom",
    "SharedDocument",
    "MeetingLink",
    "MeetingBooking",
    "Subscription",
    "SellingGuide",
    "Contract",
    "ContractAmendment",
    "Campaign",
    "CampaignMember",
    "Invoice",
    "SignatureRequest",
    "Pipeline",
    "Territory",
    "TerritoryAssignment",
    "PriceTier",
    "CustomerPricing",
    "RevenueSchedule",
    "RevenueScheduleEntry",
    "ChatSession",
    "ChatMessage",
    "AutoResponseRule",
    "SequenceStepRun",
    "DomainEvent",
    "Stakeholder",
    # V5 intelligence
    "Contact",
    "Objection",
    "ObjectionPattern",
    "ObjectionResolutionAction",
    "RecommendedActionWindow",
    "DnaPattern",
    "DnaRecommendation",
    "NetworkAnomaly",
    "NetworkPattern",
    "PlaybookAdherence",
    "PlaybookPerformance",
    "PlaybookStep",
    "DealSimilarityLink",
    "OpportunityEmbedding",
    "RepDnaProfile",
]
