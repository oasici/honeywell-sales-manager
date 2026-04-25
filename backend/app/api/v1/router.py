from fastapi import APIRouter

from app.api.v1.analytics import router as analytics_router
from app.api.v1.audit import router as audit_router
from app.api.v1.ops import router as ops_router
from app.api.v1.saved_views import router as saved_views_router
from app.api.v1.opportunities import router as opportunities_router
from app.api.v1.ai import router as ai_router
from app.api.v1.insights import router as insights_router
from app.api.v1.engagement import legacy_router as engagement_legacy_router
from app.api.v1.engagement import router as engagement_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.approvals import router as approvals_router
from app.api.v1.forecast import router as forecast_router
from app.api.v1.deal_health import router as deal_health_router
from app.api.v1.leads import router as leads_router
from app.api.v1.reports_v2 import router as reports_v2_router
from app.api.v1.teams import router as teams_router
from app.api.v1.webhooks import router as webhooks_router
from app.api.v1.coaching import router as coaching_router
from app.api.v1.cockpit import router as cockpit_router
from app.api.v1.compliance import router as compliance_router
from app.api.v1.playbooks import router as playbooks_router
from app.api.v1.field_permissions import router as field_permissions_router
from app.api.v1.product_rules import router as product_rules_router
from app.api.v1.dashboard_builder import router as dashboard_builder_router
from app.api.v1.custom_fields import router as custom_fields_router
from app.api.v1.workflow_rules import router as workflow_rules_router
from app.api.v1.activities import router as activities_router
from app.api.v1.bundles import router as bundles_router
from app.api.v1.comments import router as comments_router
from app.api.v1.email_templates import router as email_templates_router
from app.api.v1.leaderboard import router as leaderboard_router
from app.api.v1.deal_rooms import router as deal_rooms_router
from app.api.v1.documents import router as documents_router
from app.api.v1.meetings import router as meetings_router
from app.api.v1.subscriptions import router as subscriptions_router
from app.api.v1.guided_selling import router as guided_selling_router
from app.api.v1.contracts import router as contracts_router
from app.api.v1.campaigns import router as campaigns_router
from app.api.v1.invoices import router as invoices_router
from app.api.v1.signatures import router as signatures_router
from app.api.v1.pipelines import router as pipelines_router
from app.api.v1.territories import router as territories_router
from app.api.v1.revenue_recognition import router as revenue_recognition_router
from app.api.v1.chat import router as chat_router
from app.api.v1.auth import router as auth_router
from app.api.v1.pricing import router as pricing_router
from app.api.v1.stakeholders import router as stakeholders_router
from app.api.v1.customer_health import router as customer_health_router
from app.api.v1.feature_store import router as feature_store_router
from app.api.v1.buyer_state import router as buyer_state_router
from app.api.v1.decision_gaps import router as decision_gaps_router
from app.api.v1.network_benchmarks import router as network_benchmarks_router
from app.api.v1.target_alignment import router as target_alignment_router
from app.api.v1.deal_replay import router as deal_replay_router
from app.api.v1.sales_dna import router as sales_dna_router
from app.api.v1.customers import router as customers_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.duplicates import router as duplicates_router
from app.api.v1.emails import router as emails_router
from app.api.v1.notifications import router as notifications_router
from app.api.v1.parts import router as parts_router
from app.api.v1.prices import router as prices_router
from app.api.v1.quotes import router as quotes_router
from app.api.v1.settings import router as settings_router
from app.api.v1.users import router as users_router

v1_router = APIRouter()

v1_router.include_router(auth_router)
v1_router.include_router(dashboard_router)
v1_router.include_router(emails_router)
v1_router.include_router(parts_router)
v1_router.include_router(prices_router)
v1_router.include_router(customer_health_router)
v1_router.include_router(feature_store_router)
v1_router.include_router(buyer_state_router)
v1_router.include_router(decision_gaps_router)
v1_router.include_router(network_benchmarks_router)
v1_router.include_router(target_alignment_router)
v1_router.include_router(deal_replay_router)
v1_router.include_router(sales_dna_router)
v1_router.include_router(customers_router)
v1_router.include_router(quotes_router)
v1_router.include_router(analytics_router)
v1_router.include_router(notifications_router)
v1_router.include_router(settings_router)
v1_router.include_router(users_router)
v1_router.include_router(audit_router)
v1_router.include_router(ops_router)
v1_router.include_router(saved_views_router)
v1_router.include_router(opportunities_router)
v1_router.include_router(ai_router)
v1_router.include_router(insights_router)
v1_router.include_router(engagement_router)
v1_router.include_router(engagement_legacy_router)
v1_router.include_router(integrations_router)
v1_router.include_router(leads_router)
v1_router.include_router(approvals_router)
v1_router.include_router(deal_health_router)
v1_router.include_router(forecast_router)
v1_router.include_router(reports_v2_router)
v1_router.include_router(teams_router)
v1_router.include_router(webhooks_router)
v1_router.include_router(cockpit_router)
v1_router.include_router(coaching_router)
v1_router.include_router(compliance_router)
v1_router.include_router(playbooks_router)
v1_router.include_router(field_permissions_router)
v1_router.include_router(product_rules_router)
v1_router.include_router(dashboard_builder_router)
v1_router.include_router(custom_fields_router)
v1_router.include_router(workflow_rules_router)
v1_router.include_router(activities_router)
v1_router.include_router(duplicates_router)
v1_router.include_router(bundles_router)
v1_router.include_router(comments_router)
v1_router.include_router(email_templates_router)
v1_router.include_router(leaderboard_router)
v1_router.include_router(deal_rooms_router)
v1_router.include_router(documents_router)
v1_router.include_router(meetings_router)
v1_router.include_router(subscriptions_router)
v1_router.include_router(guided_selling_router)
v1_router.include_router(contracts_router)
v1_router.include_router(campaigns_router)
v1_router.include_router(invoices_router)
v1_router.include_router(signatures_router)
v1_router.include_router(pipelines_router)
v1_router.include_router(territories_router)
v1_router.include_router(revenue_recognition_router)
v1_router.include_router(chat_router)
v1_router.include_router(pricing_router)
v1_router.include_router(stakeholders_router)
