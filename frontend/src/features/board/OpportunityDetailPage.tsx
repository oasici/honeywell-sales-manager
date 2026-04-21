import { useState, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { opportunitiesApi, dealHealthApi, forecastApi, aiApi, dealRoomsApi } from '../../lib/api';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { formatCurrency, formatDateTime, formatDate } from '../../lib/formatters';
import { useAuthStore } from '../../stores/authStore';
import { useT } from '../../hooks/useT';
import SalesPathBar from './SalesPathBar';
import ActivityLogPanel from './ActivityLogPanel';
import CommentThread from './CommentThread';
import BuyerRelationshipMap from '../opportunities/BuyerRelationshipMap';
import type {
  Opportunity,
  OpportunityEvent,
  DealHealthReport,
  ForecastAdjustment,
  DealRiskResult,
  AiSummarizeResponse,
  CloseProbabilityResult,
  ActivitySummary,
  DealRoom,
} from '../../lib/types';

const RISK_BADGE_VARIANT: Record<string, 'success' | 'warning' | 'danger'> = {
  healthy: 'success',
  at_risk: 'warning',
  critical: 'danger',
};

const SCORE_RING_RADIUS = 36;
const SCORE_RING_CIRCUMFERENCE = 2 * Math.PI * SCORE_RING_RADIUS;

function ScoreRing({ score }: { score: number }) {
  const color = score >= 70 ? '#22c55e' : score >= 40 ? '#f59e0b' : '#ef4444';
  const pct = Math.min(score, 100);
  const offset = SCORE_RING_CIRCUMFERENCE - (pct / 100) * SCORE_RING_CIRCUMFERENCE;

  return (
    <div className="relative h-24 w-24">
      <svg className="h-24 w-24 -rotate-90" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r="36" stroke="#e5e7eb" strokeWidth="6" fill="none" />
        <circle
          cx="40"
          cy="40"
          r="36"
          stroke={color}
          strokeWidth="6"
          fill="none"
          strokeDasharray={SCORE_RING_CIRCUMFERENCE}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-xl font-bold text-gray-900 dark:text-white">{score}</span>
      </div>
    </div>
  );
}

export default function OpportunityDetailPage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const oppId = Number(id);

  const STAGE_LABELS = useMemo(
    () => ({
      prospecting: t('opp_detail.stage_prospecting'),
      qualified: t('opp_detail.stage_qualified'),
      proposal: t('opp_detail.stage_proposal'),
      negotiation: t('opp_detail.stage_negotiation'),
      closed_won: t('opp_detail.stage_closed_won'),
      closed_lost: t('opp_detail.stage_closed_lost'),
    }),
    [t],
  );

  const RISK_LABELS = useMemo(
    () => ({
      healthy: t('opp_detail.risk_healthy'),
      at_risk: t('opp_detail.risk_at_risk'),
      critical: t('opp_detail.risk_critical'),
    }),
    [t],
  );

  const FORECAST_CATEGORIES = useMemo(
    () => [
      { value: 'commit', label: t('opp_detail.fc_commit') },
      { value: 'best_case', label: t('opp_detail.fc_best_case') },
      { value: 'pipeline', label: t('opp_detail.fc_pipeline') },
      { value: 'omitted', label: t('opp_detail.fc_omitted') },
    ],
    [t],
  );

  const { data: opp, isLoading } = useQuery<Opportunity>({
    queryKey: ['opportunity', oppId],
    queryFn: () => opportunitiesApi.get(oppId),
    enabled: !!oppId,
  });

  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isManager = user?.role === 'manager' || user?.role === 'admin';

  const { data: timelineData } = useQuery<{ events: OpportunityEvent[] }>({
    queryKey: ['opportunity-timeline', oppId],
    queryFn: () => opportunitiesApi.getTimeline(oppId),
    enabled: !!oppId,
  });

  const { data: activitySummary, isLoading: activitySummaryLoading } = useQuery<ActivitySummary>({
    queryKey: ['activity-summary', oppId],
    queryFn: () => opportunitiesApi.getActivitySummary(oppId),
    enabled: !!oppId,
  });

  const { data: dealHealth, isLoading: healthLoading } = useQuery<DealHealthReport>({
    queryKey: ['deal-health', oppId],
    queryFn: () => dealHealthApi.get(oppId),
    enabled: !!oppId,
  });

  const { data: adjustmentsData, isLoading: adjLoading } = useQuery<{
    adjustments: ForecastAdjustment[];
  }>({
    queryKey: ['forecast-adjustments', oppId],
    queryFn: () => forecastApi.getAdjustments(oppId),
    enabled: !!oppId,
  });

  // AI queries
  const { data: aiRisk, isLoading: aiRiskLoading } = useQuery<DealRiskResult>({
    queryKey: ['ai-deal-risk', oppId],
    queryFn: () => aiApi.dealRisk(oppId),
    enabled: !!oppId,
    retry: false,
  });

  const { data: aiSummary, isLoading: aiSummaryLoading } = useQuery<AiSummarizeResponse>({
    queryKey: ['ai-opp-summary', oppId],
    queryFn: () => aiApi.summarize({ entity_type: 'opportunity', entity_id: oppId }),
    enabled: !!oppId,
    retry: false,
  });

  const { data: closePrediction, isLoading: closePredictionLoading } = useQuery<{
    data: CloseProbabilityResult;
  }>({
    queryKey: ['ai-predict-close', oppId],
    queryFn: () => aiApi.predictClose(oppId),
    enabled: !!oppId,
    retry: false,
  });

  const { data: dealRoomsData, isLoading: dealRoomsLoading } = useQuery<{ deal_rooms: DealRoom[] }>(
    {
      queryKey: ['deal-rooms'],
      queryFn: () => dealRoomsApi.list(),
      enabled: !!oppId,
    },
  );

  const oppDealRooms = (dealRoomsData?.deal_rooms ?? []).filter((r) => r.opportunity_id === oppId);

  const createDealRoomMutation = useMutation({
    mutationFn: () =>
      dealRoomsApi.create({
        opportunity_id: oppId,
        name: `${opp?.title ?? t('opp_detail.opportunity_fallback')} - ${t('opp_detail.deal_room_title')}`,
      }),
    onSuccess: () => {
      toast.success(t('opp_detail.toast_deal_room_ok'));
      queryClient.invalidateQueries({ queryKey: ['deal-rooms'] });
    },
    onError: () => toast.error(t('opp_detail.toast_deal_room_fail')),
  });

  const generateActionsMutation = useMutation({
    mutationFn: () => aiApi.generateActions({ opportunity_id: oppId }),
    onSuccess: (data: { actions: unknown[]; count: number }) => {
      toast.success(`${data.count} ${t('opp_detail.toast_ai_tasks_suffix')}`);
      queryClient.invalidateQueries({ queryKey: ['ai-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['cockpit'] });
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  const [adjForm, setAdjForm] = useState({
    new_amount: '',
    new_category: 'pipeline',
    reason: '',
  });

  const adjustmentMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => forecastApi.createAdjustment(payload),
    onSuccess: () => {
      toast.success(t('opp_detail.toast_forecast_saved'));
      queryClient.invalidateQueries({ queryKey: ['forecast-adjustments', oppId] });
      setAdjForm({ new_amount: '', new_category: 'pipeline', reason: '' });
    },
  });

  if (isLoading) {
    return <Skeleton variant="card" count={3} />;
  }

  if (!opp) {
    return <div className="py-16 text-center text-gray-500">{t('opp_detail.not_found')}</div>;
  }

  const events = timelineData?.events || [];

  return (
    <div>
      <PageHeader
        title={opp.title}
        description={STAGE_LABELS[opp.stage as keyof typeof STAGE_LABELS] || opp.stage}
      >
        <Button variant="secondary" onClick={() => navigate('/board')}>
          {t('opp_detail.back_board')}
        </Button>
      </PageHeader>

      <SalesPathBar oppId={oppId} currentStage={opp.stage} />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left: Details */}
        <div className="lg:col-span-2 space-y-6">
          <Card title={t('opp_detail.card_info')}>
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {t('opp_detail.lbl_stage')}
                </span>
                <p className="font-semibold text-gray-900 dark:text-white">
                  {STAGE_LABELS[opp.stage as keyof typeof STAGE_LABELS] || opp.stage}
                </p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {t('opp_detail.lbl_amount')}
                </span>
                <p className="font-semibold text-gray-900 dark:text-white">
                  {opp.amount != null ? formatCurrency(opp.amount, opp.currency) : '-'}
                </p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {t('opp_detail.lbl_close')}
                </span>
                <p className="text-gray-700 dark:text-gray-300">{opp.close_date || '-'}</p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {t('opp_detail.lbl_owner')}
                </span>
                <p className="text-gray-700 dark:text-gray-300">{opp.owner?.full_name || '-'}</p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {t('opp_detail.lbl_customer')}
                </span>
                <p className="text-gray-700 dark:text-gray-300">
                  {opp.customer ? `${opp.customer.name} (${opp.customer.company})` : '-'}
                </p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {t('opp_detail.lbl_rotting')}
                </span>
                <p
                  className={`font-semibold ${opp.rotting_days > 7 ? 'text-red-600' : 'text-gray-700 dark:text-gray-300'}`}
                >
                  {opp.rotting_days} {t('opp_detail.days_suffix')}
                </p>
              </div>
            </div>
          </Card>

          {/* Related Quotes */}
          {opp.quotes && opp.quotes.length > 0 && (
            <Card title={t('opp_detail.related_quotes')}>
              <div className="space-y-2">
                {opp.quotes.map((q) => (
                  <button
                    key={q.id}
                    type="button"
                    onClick={() => navigate(`/quotes/${q.id}`)}
                    className="flex w-full items-center justify-between rounded-lg border border-gray-200 px-4 py-3 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
                  >
                    <span className="font-mono text-sm font-semibold text-gray-900 dark:text-white">
                      {q.quote_number}
                    </span>
                    <div className="flex items-center gap-3">
                      <Badge variant="default" size="sm">
                        {q.status}
                      </Badge>
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        {formatCurrency(q.grand_total, opp.currency)}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            </Card>
          )}
        </div>

        {/* Right: Timeline */}
        <div>
          <Card title={t('opp_detail.timeline')}>
            {events.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-400">
                {t('opp_detail.timeline_empty')}
              </p>
            ) : (
              <div className="space-y-0">
                {events.map((event, idx) => (
                  <div key={event.id} className="relative flex gap-3 pb-4">
                    {/* Line */}
                    {idx < events.length - 1 && (
                      <div className="absolute left-[11px] top-6 h-full w-0.5 bg-gray-200 dark:bg-gray-700" />
                    )}
                    {/* Dot */}
                    <div className="relative z-10 mt-1 h-6 w-6 shrink-0 rounded-full bg-gray-100 flex items-center justify-center dark:bg-gray-700">
                      <div
                        className={`h-2.5 w-2.5 rounded-full ${
                          event.event_type === 'stage_change' ? 'bg-blue-500' : 'bg-gray-400'
                        }`}
                      />
                    </div>
                    {/* Content */}
                    <div className="min-w-0">
                      <p className="text-sm text-gray-900 dark:text-white">
                        {event.description || event.event_type}
                      </p>
                      <p className="text-[10px] text-gray-400">
                        {formatDateTime(event.occurred_at)}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* Deal Health Section */}
      <div className="mt-6">
        <Card title={t('opp_detail.deal_health')}>
          {healthLoading ? (
            <Skeleton variant="card" />
          ) : dealHealth ? (
            <div className="space-y-6">
              {/* Score ring + risk badge */}
              <div className="flex items-center gap-6">
                <ScoreRing score={dealHealth.score} />
                <div>
                  <Badge variant={RISK_BADGE_VARIANT[dealHealth.risk_level] || 'default'}>
                    {RISK_LABELS[dealHealth.risk_level as keyof typeof RISK_LABELS] ||
                      dealHealth.risk_level}
                  </Badge>
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    {t('opp_detail.health_score_hint')}
                  </p>
                </div>
              </div>

              {/* Indicators */}
              <div className="space-y-3">
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300">
                  {t('opp_detail.indicators')}
                </h4>
                {dealHealth.indicators.map((ind) => (
                  <div key={ind.name}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-gray-700 dark:text-gray-300">{ind.label}</span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {ind.score}/100 ({t('opp_detail.weight')}: {ind.weight})
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-gray-100 dark:bg-gray-800">
                      <div
                        className={`h-2 rounded-full transition-all duration-500 ${
                          ind.score >= 70
                            ? 'bg-green-500'
                            : ind.score >= 40
                              ? 'bg-amber-500'
                              : 'bg-red-500'
                        }`}
                        style={{ width: `${Math.max(ind.score, 2)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              {/* Recommendations */}
              {dealHealth.recommendations.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                    {t('opp_detail.recommendations')}
                  </h4>
                  <ul className="space-y-1.5">
                    {dealHealth.recommendations.map((rec, idx) => (
                      <li
                        key={idx}
                        className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400"
                      >
                        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" />
                        {rec}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-gray-400">{t('opp_detail.health_empty')}</p>
          )}
        </Card>
      </div>

      {/* AI Insights Section */}
      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* AI Risk Assessment */}
        <Card title={t('opp_detail.ai_risk_title')}>
          {aiRiskLoading ? (
            <Skeleton variant="card" />
          ) : aiRisk ? (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <ScoreRing score={aiRisk.risk_score} />
                <div>
                  <Badge
                    variant={
                      aiRisk.risk_level === 'low'
                        ? 'success'
                        : aiRisk.risk_level === 'critical'
                          ? 'danger'
                          : 'warning'
                    }
                  >
                    {aiRisk.risk_level === 'low'
                      ? t('opp_detail.ai_risk_low')
                      : aiRisk.risk_level === 'medium'
                        ? t('opp_detail.ai_risk_medium')
                        : aiRisk.risk_level === 'high'
                          ? t('opp_detail.ai_risk_high')
                          : t('opp_detail.ai_risk_critical')}
                  </Badge>
                  <p className="mt-1 text-xs text-gray-500">{t('opp_detail.claude_evaluated')}</p>
                </div>
              </div>
              {aiRisk.factors && aiRisk.factors.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-gray-500 uppercase">
                    {t('opp_detail.risk_factors')}
                  </h4>
                  {aiRisk.factors.map((f, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded-lg bg-gray-50 dark:bg-gray-800 px-3 py-2"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-white">
                          {f.name}
                        </p>
                        <p className="text-xs text-gray-500 truncate">{f.description}</p>
                      </div>
                      <span
                        className={`text-sm font-bold ${f.score >= 70 ? 'text-red-600' : f.score >= 40 ? 'text-amber-600' : 'text-green-600'}`}
                      >
                        {f.score}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {aiRisk.recommendations && aiRisk.recommendations.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">
                    {t('opp_detail.ai_suggestions')}
                  </h4>
                  <ul className="space-y-1">
                    {aiRisk.recommendations.map((r, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400"
                      >
                        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-honeywell-red" />
                        {r}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <Button
                size="sm"
                variant="secondary"
                loading={generateActionsMutation.isPending}
                onClick={() => generateActionsMutation.mutate()}
              >
                {t('opp_detail.btn_ai_actions')}
              </Button>
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-gray-400">
              {t('opp_detail.ai_risk_empty')}
            </p>
          )}
        </Card>

        {/* Close Probability */}
        <Card title={t('opp_detail.close_probability')}>
          {closePredictionLoading ? (
            <Skeleton variant="card" />
          ) : closePrediction?.data ? (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <ScoreRing score={closePrediction.data.close_probability} />
                <div>
                  <Badge
                    variant={
                      closePrediction.data.confidence === 'high'
                        ? 'success'
                        : closePrediction.data.confidence === 'medium'
                          ? 'warning'
                          : 'danger'
                    }
                  >
                    {closePrediction.data.confidence === 'high'
                      ? t('opp_detail.conf_high')
                      : closePrediction.data.confidence === 'medium'
                        ? t('opp_detail.conf_medium')
                        : t('opp_detail.conf_low')}
                  </Badge>
                  <p className="mt-1 text-xs text-gray-500">{t('opp_detail.close_prob_hint')}</p>
                </div>
              </div>
              {closePrediction.data.factors && closePrediction.data.factors.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-gray-500 uppercase">
                    {t('opp_detail.influencing_factors')}
                  </h4>
                  {closePrediction.data.factors.map((f, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded-lg bg-gray-50 dark:bg-gray-800 px-3 py-2"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-gray-900 dark:text-white">
                          {f.name}
                        </p>
                        <p className="text-xs text-gray-500 truncate">{f.evidence}</p>
                      </div>
                      <Badge
                        variant={
                          f.impact === 'positive'
                            ? 'success'
                            : f.impact === 'negative'
                              ? 'danger'
                              : 'default'
                        }
                        size="sm"
                      >
                        {f.impact === 'positive'
                          ? t('opp_detail.impact_positive')
                          : f.impact === 'negative'
                            ? t('opp_detail.impact_negative')
                            : t('opp_detail.impact_neutral')}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
              {closePrediction.data.next_steps && closePrediction.data.next_steps.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold text-gray-500 uppercase mb-1">
                    {t('opp_detail.next_steps')}
                  </h4>
                  <ul className="space-y-1">
                    {closePrediction.data.next_steps.map((step, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-400"
                      >
                        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-500" />
                        {step}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-gray-400">
              {t('opp_detail.close_data_empty')}
            </p>
          )}
        </Card>

        {/* AI Summary */}
        <Card title={t('opp_detail.ai_summary')}>
          {aiSummaryLoading ? (
            <Skeleton variant="card" />
          ) : aiSummary ? (
            <div className="space-y-3">
              <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap leading-relaxed">
                {aiSummary.summary}
              </p>
              {aiSummary.sources && aiSummary.sources.length > 0 && (
                <p className="text-xs text-gray-400">
                  {t('opp_detail.sources')}: {aiSummary.sources.join(', ')}
                </p>
              )}
              {aiSummary.cached && (
                <Badge variant="default" size="sm">
                  {t('opp_detail.cached')}
                </Badge>
              )}
              {/* Cross-link to customer */}
              {opp.customer_id && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => navigate(`/customers/${opp.customer_id}`)}
                >
                  {t('opp_detail.customer_health_cta')} &rarr;
                </Button>
              )}
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-gray-400">
              {t('opp_detail.ai_summary_empty')}
            </p>
          )}
        </Card>
      </div>

      {/* Forecast Adjustments Section */}
      <div className="mt-6">
        <Card title={t('opp_detail.forecast_adj')}>
          {adjLoading ? (
            <Skeleton variant="card" />
          ) : (
            <div className="space-y-6">
              {/* History table */}
              {adjustmentsData?.adjustments && adjustmentsData.adjustments.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 dark:border-gray-700">
                        <th className="py-2 px-3 text-left text-xs text-gray-500">
                          {t('opp_detail.tbl_date')}
                        </th>
                        <th className="py-2 px-3 text-right text-xs text-gray-500">
                          {t('opp_detail.tbl_orig_amount')}
                        </th>
                        <th className="py-2 px-3 text-right text-xs text-gray-500">
                          {t('opp_detail.tbl_new_amount')}
                        </th>
                        <th className="py-2 px-3 text-left text-xs text-gray-500">
                          {t('opp_detail.tbl_category')}
                        </th>
                        <th className="py-2 px-3 text-left text-xs text-gray-500">
                          {t('opp_detail.tbl_reason')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {adjustmentsData.adjustments.map((adj) => (
                        <tr key={adj.id} className="border-b border-gray-50 dark:border-gray-800">
                          <td className="py-2 px-3 text-xs text-gray-600 dark:text-gray-400">
                            {adj.created_at ? formatDate(adj.created_at) : '-'}
                          </td>
                          <td className="py-2 px-3 text-right text-xs">
                            {formatCurrency(adj.original_amount, opp.currency)}
                          </td>
                          <td className="py-2 px-3 text-right text-xs font-semibold">
                            {formatCurrency(adj.adjusted_amount, opp.currency)}
                          </td>
                          <td className="py-2 px-3 text-xs">
                            {adj.original_category !== adj.adjusted_category ? (
                              <span>
                                {adj.original_category} &rarr; {adj.adjusted_category}
                              </span>
                            ) : (
                              adj.adjusted_category
                            )}
                          </td>
                          <td className="py-2 px-3 text-xs text-gray-500 dark:text-gray-400 max-w-[200px] truncate">
                            {adj.reason || '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="py-4 text-center text-sm text-gray-400">{t('opp_detail.adj_none')}</p>
              )}

              {/* Adjustment form (manager only) */}
              {isManager && (
                <div className="border-t border-gray-100 dark:border-gray-700 pt-4">
                  <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
                    {t('opp_detail.new_adj')}
                  </h4>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                        {t('opp_detail.lbl_new_amount')}
                      </label>
                      <input
                        type="number"
                        value={adjForm.new_amount}
                        onChange={(e) => setAdjForm((f) => ({ ...f, new_amount: e.target.value }))}
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                        placeholder="0.00"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                        {t('opp_detail.lbl_category')}
                      </label>
                      <select
                        value={adjForm.new_category}
                        onChange={(e) =>
                          setAdjForm((f) => ({ ...f, new_category: e.target.value }))
                        }
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                      >
                        {FORECAST_CATEGORIES.map((cat) => (
                          <option key={cat.value} value={cat.value}>
                            {cat.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                        {t('opp_detail.lbl_reason')}
                      </label>
                      <textarea
                        value={adjForm.reason}
                        onChange={(e) => setAdjForm((f) => ({ ...f, reason: e.target.value }))}
                        rows={1}
                        className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
                        placeholder={t('opp_detail.reason_ph')}
                      />
                    </div>
                  </div>
                  <div className="mt-3 flex justify-end">
                    <Button
                      size="sm"
                      loading={adjustmentMutation.isPending}
                      disabled={!adjForm.new_amount}
                      onClick={() => {
                        adjustmentMutation.mutate({
                          opportunity_id: oppId,
                          adjusted_amount: Number(adjForm.new_amount),
                          adjusted_category: adjForm.new_category,
                          reason: adjForm.reason || null,
                        });
                      }}
                    >
                      {t('common.save')}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </Card>
      </div>

      {/* Activity Summary (Modul 6) */}
      <div className="mt-6">
        <Card title={t('opp_detail.activity_summary')}>
          {activitySummaryLoading ? (
            <Skeleton variant="card" />
          ) : activitySummary ? (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 text-sm">
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {t('opp_detail.total_activities')}
                </span>
                <p className="text-xl font-bold text-gray-900 dark:text-white">
                  {activitySummary.total_activities}
                </p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {t('opp_detail.since_last')}
                </span>
                <p
                  className={`text-xl font-bold ${activitySummary.days_since_last_activity > 7 ? 'text-red-600' : 'text-gray-900 dark:text-white'}`}
                >
                  {activitySummary.days_since_last_activity} {t('opp_detail.days_suffix')}
                </p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {t('opp_detail.avg_stage')}
                </span>
                <p className="text-xl font-bold text-gray-900 dark:text-white">
                  {activitySummary.avg_activities_for_stage}
                </p>
              </div>
              <div>
                <span className="text-xs text-gray-500 dark:text-gray-400">
                  {t('opp_detail.by_type')}
                </span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {Object.entries(activitySummary.by_type).map(([type, count]) => (
                    <Badge key={type} variant="default" size="sm">
                      {type}: {count}
                    </Badge>
                  ))}
                  {Object.keys(activitySummary.by_type).length === 0 && (
                    <span className="text-xs text-gray-400">-</span>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <p className="py-4 text-center text-sm text-gray-400">
              {t('opp_detail.activity_empty')}
            </p>
          )}
        </Card>
      </div>

      {/* Deal Room Section */}
      <div className="mt-6">
        <Card title={t('opp_detail.deal_room_title')}>
          {dealRoomsLoading ? (
            <Skeleton variant="card" />
          ) : oppDealRooms.length > 0 ? (
            <div className="space-y-2">
              {oppDealRooms.map((room) => (
                <button
                  key={room.id}
                  type="button"
                  onClick={() => navigate(`/deal-rooms/${room.id}`)}
                  className="flex w-full items-center justify-between rounded-lg border border-gray-200 px-4 py-3 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800"
                >
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">
                    {room.name}
                  </span>
                  <div className="flex items-center gap-2">
                    {room.last_buyer_activity_at && (
                      <Badge variant="default" size="sm">
                        {t('opp_detail.last_activity')}:{' '}
                        {formatDateTime(room.last_buyer_activity_at)}
                      </Badge>
                    )}
                    <Badge variant={room.is_active ? 'success' : 'danger'} size="sm">
                      {room.is_active ? t('opp_detail.active') : t('opp_detail.inactive')}
                    </Badge>
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <div className="py-4 text-center">
              <p className="mb-3 text-sm text-gray-400">{t('opp_detail.dr_empty')}</p>
              <Button
                size="sm"
                loading={createDealRoomMutation.isPending}
                onClick={() => createDealRoomMutation.mutate()}
              >
                {t('opp_detail.dr_create')}
              </Button>
            </div>
          )}
        </Card>
      </div>

      {/* Buyer Relationship Map */}
      <div className="mt-6">
        <Card title={t('opp_detail.buying_map')}>
          <BuyerRelationshipMap opportunityId={oppId} />
        </Card>
      </div>

      {/* Activity Log Section */}
      <div className="mt-6">
        <ActivityLogPanel opportunityId={oppId} />
      </div>

      {/* Comments Section */}
      <div className="mt-6">
        <CommentThread entityType="opportunity" entityId={oppId} />
      </div>
    </div>
  );
}
