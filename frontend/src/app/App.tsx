import { lazy, Suspense, useEffect } from 'react';
import { Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { AuthGuard } from '../features/auth/AuthGuard';
import { LoginPage } from '../features/auth/LoginPage';
import { Layout } from '../components/layout/Layout';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { ErrorBoundary } from '../components/ui/ErrorBoundary';
import { usePreferencesStore } from '../stores/preferencesStore';

const DashboardPage = lazy(() => import('../features/dashboard/DashboardPage'));
const EmailListPage = lazy(() => import('../features/emails/EmailListPage'));
const EmailDetailPage = lazy(() => import('../features/emails/EmailDetailPage'));
const EmailTemplatesPage = lazy(() => import('../features/emails/EmailTemplatesPage'));
const PartsPage = lazy(() => import('../features/parts/PartsPage'));
const QuoteListPage = lazy(() => import('../features/quotes/QuoteListPage'));
const QuoteEditorPage = lazy(() => import('../features/quotes/QuoteEditorPage'));
const CustomerListPage = lazy(() => import('../features/customers/CustomerListPage'));
const CustomerDetailPage = lazy(() => import('../features/customers/CustomerDetailPage'));
const HighIntentAccountsPage = lazy(() => import('../features/customers/HighIntentAccountsPage'));
const SettingsPage = lazy(() => import('../features/settings/SettingsPage'));
const ReportsPage = lazy(() => import('../features/admin/ReportsPage'));
const UserManagementPage = lazy(() => import('../features/admin/UserManagementPage'));
const AuditLogPage = lazy(() => import('../features/admin/AuditLogPage'));
const DataExportPage = lazy(() => import('../features/admin/DataExportPage'));

// v2 pages (behind FEATURE_V2_BOARD flag)
const BoardPage = lazy(() => import('../features/board/BoardPage'));
const PlanningStudioPage = lazy(() => import('../features/planning/PlanningStudioPage'));
const OpportunityDetailPage = lazy(() => import('../features/board/OpportunityDetailPage'));
const SalesAnalyticsPage = lazy(() => import('../features/board/SalesAnalyticsPage'));
const DealRoomPage = lazy(() => import('../features/board/DealRoomPage'));
const OpportunitiesHomePage = lazy(() => import('../features/opportunities/OpportunitiesHomePage'));

// Lead lifecycle (feature-flag controlled at API level)
const LeadListPage = lazy(() => import('../features/leads/LeadListPage'));
const LeadDetailPage = lazy(() => import('../features/leads/LeadDetailPage'));

// Approval routing
const PendingApprovalsPage = lazy(() => import('../features/approvals/PendingApprovalsPage'));
const ApprovalRulesPage = lazy(() => import('../features/approvals/ApprovalRulesPage'));

// Revenue Cockpit
const CockpitPage = lazy(() => import('../features/cockpit/CockpitPage'));

// Report Builder (FAZ-5)
const ReportBuilderPage = lazy(() => import('../features/reports/ReportBuilderPage'));
const SavedReportsPage = lazy(() => import('../features/reports/SavedReportsPage'));
const ReportViewPage = lazy(() => import('../features/reports/ReportViewPage'));

// AI Engine
const AiTasksPage = lazy(() => import('../features/ai/AiTasksPage'));
const AiInsightsPage = lazy(() => import('../features/ai/AiInsightsPage'));
const InsightsPage = lazy(() => import('../features/insights/InsightsPage'));

// Dashboard Builder
const DashboardListPage = lazy(() => import('../features/dashboards/DashboardListPage'));
const DashboardEditorPage = lazy(() => import('../features/dashboards/DashboardEditorPage'));

// Playbooks
const PlaybookListPage = lazy(() => import('../features/playbooks/PlaybookListPage'));
const PlaybookDetailPage = lazy(() => import('../features/playbooks/PlaybookDetailPage'));
const PlaybookTemplatesPage = lazy(() => import('../features/playbooks/PlaybookTemplatesPage'));
const PlaybookAnalyticsPage = lazy(() => import('../features/playbooks/PlaybookAnalyticsPage'));

// Coaching
const CoachingOverviewPage = lazy(() => import('../features/coaching/CoachingOverviewPage'));
const CoachingRepPage = lazy(() => import('../features/coaching/CoachingRepPage'));

// Engagement
const TranscriptsPage = lazy(() => import('../features/engagement/TranscriptsPage'));
const KeywordPacksPage = lazy(() => import('../features/engagement/KeywordPacksPage'));
const SequencesPage = lazy(() => import('../features/engagement/SequencesPage'));
const SequenceBuilderPage = lazy(() => import('../features/engagement/SequenceBuilderPage'));
const SegmentsPage = lazy(() => import('../features/engagement/SegmentsPage'));
const ScorecardsPage = lazy(() => import('../features/engagement/ScorecardsPage'));

// Compliance (KVKK)
const ComplianceDashboardPage = lazy(
  () => import('../features/compliance/ComplianceDashboardPage'),
);
const RetentionPoliciesPage = lazy(() => import('../features/compliance/RetentionPoliciesPage'));
const BreachWorkflowPage = lazy(() => import('../features/compliance/BreachWorkflowPage'));

// Integrations
const IntegrationsPage = lazy(() => import('../features/integrations/IntegrationsPage'));

// Leaderboard, Data Quality & At-Risk
const LeaderboardPage = lazy(() => import('../features/admin/LeaderboardPage'));
const DataQualityPage = lazy(() => import('../features/admin/DataQualityPage'));
const AtRiskPage = lazy(() => import('../features/board/AtRiskPage'));

// Admin Extensions
const CustomFieldsPage = lazy(() => import('../features/admin/CustomFieldsPage'));
const FieldPermissionsPage = lazy(() => import('../features/admin/FieldPermissionsPage'));
const ProductRulesPage = lazy(() => import('../features/admin/ProductRulesPage'));
const WorkflowRulesPage = lazy(() => import('../features/admin/WorkflowRulesPage'));
const FlowBuilderPage = lazy(() => import('../features/admin/FlowBuilderPage'));
const MergeRecordsPage = lazy(() => import('../features/admin/MergeRecordsPage'));

// Subscriptions
const SubscriptionListPage = lazy(() => import('../features/subscriptions/SubscriptionListPage'));
const SubscriptionDetailPage = lazy(
  () => import('../features/subscriptions/SubscriptionDetailPage'),
);

// Contracts
const ContractListPage = lazy(() => import('../features/contracts/ContractListPage'));
const ContractDetailPage = lazy(() => import('../features/contracts/ContractDetailPage'));

// Campaigns
const CampaignListPage = lazy(() => import('../features/campaigns/CampaignListPage'));
const CampaignDetailPage = lazy(() => import('../features/campaigns/CampaignDetailPage'));

// Invoices
const InvoiceListPage = lazy(() => import('../features/invoices/InvoiceListPage'));
const InvoiceDetailPage = lazy(() => import('../features/invoices/InvoiceDetailPage'));

// E-Signature (public)
const SigningPage = lazy(() => import('../features/esign/SigningPage'));

// Pipeline Settings
const PipelineSettingsPage = lazy(() => import('../features/settings/PipelineSettingsPage'));

// Territory Management
const TerritoryPage = lazy(() => import('../features/admin/TerritoryPage'));

// Pricing Admin
const PricingAdminPage = lazy(() => import('../features/admin/PricingAdminPage'));

// Revenue Recognition
const RevenueRecognitionPage = lazy(() => import('../features/revenue/RevenueRecognitionPage'));

// Agent Chat
const AgentChatPage = lazy(() => import('../features/chat/AgentChatPage'));

// Marketing landing page (public, no auth)
const LandingPage = lazy(() => import('../features/landing/LandingPage'));

export default function App() {
  // Force a top-level rerender on language changes so non-hook consumers
  // (formatters, option lists, etc.) update consistently.
  usePreferencesStore((s) => s.language);

  const navigate = useNavigate();

  useEffect(() => {
    function handleGlobalKeys(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        navigate('/cockpit');
      }
    }
    window.addEventListener('keydown', handleGlobalKeys);
    return () => window.removeEventListener('keydown', handleGlobalKeys);
  }, [navigate]);

  return (
    <Routes>
      <Route
        path="/landing"
        element={
          <Suspense fallback={<LoadingSpinner />}>
            <LandingPage />
          </Suspense>
        }
      />
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/sign/:token"
        element={
          <Suspense fallback={<LoadingSpinner />}>
            <SigningPage />
          </Suspense>
        }
      />

      <Route
        path="/"
        element={
          <AuthGuard>
            <Layout />
          </AuthGuard>
        }
      >
        <Route
          index
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <DashboardPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="cockpit"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <CockpitPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="emails"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <EmailListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="emails/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <EmailDetailPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="parts"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <PartsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="quotes"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <QuoteListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="quotes/new"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <QuoteEditorPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="quotes/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <QuoteEditorPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="customers"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <CustomerListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="customers/high-intent"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <HighIntentAccountsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="customers/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <CustomerDetailPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="settings"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <SettingsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="reports"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <ReportsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="users"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <UserManagementPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="audit"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <AuditLogPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="kvkk-export"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <DataExportPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Lead Lifecycle (feature-flag controlled at API level) */}
        <Route
          path="leads"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <LeadListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="leads/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <LeadDetailPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Approval Routing */}
        <Route
          path="approvals"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <PendingApprovalsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="approvals/rules"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <ApprovalRulesPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Report Builder (FAZ-5) */}
        <Route
          path="reports/builder"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <ReportBuilderPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="reports/saved"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <SavedReportsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="reports/view/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <ReportViewPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* v2: Sales Board (feature-flag controlled at API level) */}
        <Route
          path="board"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <BoardPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="planning-studio"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <PlanningStudioPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="opportunities"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <OpportunitiesHomePage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="opportunities/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <OpportunityDetailPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="deal-rooms/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <DealRoomPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="sales-analytics"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <SalesAnalyticsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* AI Engine */}
        <Route
          path="ai/tasks"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <AiTasksPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="ai/insights"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <AiInsightsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="insights"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <InsightsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Dashboard Builder */}
        <Route
          path="dashboards"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <DashboardListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="dashboards/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <DashboardEditorPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Playbooks */}
        <Route
          path="playbooks"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <PlaybookListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="playbooks/templates"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <PlaybookTemplatesPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="playbooks/analytics"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <PlaybookAnalyticsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="playbooks/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <PlaybookDetailPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Coaching */}
        <Route
          path="coaching"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <CoachingOverviewPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="coaching/rep/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <CoachingRepPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Engagement */}
        <Route
          path="engagement/transcripts"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <TranscriptsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="engagement/keywords"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <KeywordPacksPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="engagement/sequences"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <SequencesPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="engagement/sequences/builder"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <SequenceBuilderPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="engagement/sequences/:id/edit"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <SequenceBuilderPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="engagement/segments"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <SegmentsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="engagement/scorecards"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <ScorecardsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Compliance (KVKK) */}
        <Route
          path="compliance"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <ComplianceDashboardPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="compliance/retention"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <RetentionPoliciesPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="compliance/breaches"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <BreachWorkflowPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Integrations */}
        <Route
          path="integrations"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <IntegrationsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Email Templates */}
        <Route
          path="email-templates"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <EmailTemplatesPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* At-Risk Opportunities */}
        <Route
          path="at-risk"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <AtRiskPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Leaderboard */}
        <Route
          path="leaderboard"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <LeaderboardPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Data Quality */}
        <Route
          path="admin/data-quality"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <DataQualityPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Subscriptions */}
        <Route
          path="subscriptions"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <SubscriptionListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="subscriptions/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <SubscriptionDetailPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Admin Extensions */}
        <Route
          path="admin/custom-fields"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <CustomFieldsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="admin/field-permissions"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <FieldPermissionsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="admin/product-rules"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <ProductRulesPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="admin/workflow-rules"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <WorkflowRulesPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="admin/workflow-rules/flow/new"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <FlowBuilderPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="admin/workflow-rules/flow/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <FlowBuilderPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="admin/merge/:entityType/:winnerId/:loserId"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <MergeRecordsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Contracts */}
        <Route
          path="contracts"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <ContractListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="contracts/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <ContractDetailPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Campaigns */}
        <Route
          path="campaigns"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <CampaignListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="campaigns/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <CampaignDetailPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Invoices */}
        <Route
          path="invoices"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <InvoiceListPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
        <Route
          path="invoices/:id"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <InvoiceDetailPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Pipeline Settings */}
        <Route
          path="settings/pipelines"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <PipelineSettingsPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Territory Management */}
        <Route
          path="admin/territories"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <TerritoryPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Pricing Admin */}
        <Route
          path="admin/pricing"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <PricingAdminPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Revenue Recognition */}
        <Route
          path="revenue-recognition"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <RevenueRecognitionPage />
              </ErrorBoundary>
            </Suspense>
          }
        />

        {/* Agent Chat */}
        <Route
          path="admin/chat"
          element={
            <Suspense fallback={<LoadingSpinner />}>
              <ErrorBoundary>
                <AgentChatPage />
              </ErrorBoundary>
            </Suspense>
          }
        />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
