import { useState, useMemo, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { onOpportunityChanged } from '../../lib/cacheInvalidation';
import { toast } from 'sonner';
import { Calendar } from 'lucide-react';
import {
  opportunitiesApi,
  forecastApi,
  aiApi,
  dealRoomsApi,
  meetingsApi,
  v4Api,
  buyerStateApi,
  decisionGapsApi,
  networkBenchmarksApi,
} from '../../lib/api';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { formatCurrency, formatDateTime, formatDate } from '../../lib/formatters';
import { useAuthStore } from '../../stores/authStore';
import { useT } from '../../hooks/useT';
import {
  translateActivityType,
  translateBuyerState,
  translateGapType,
  translateMomentumBand,
  translateSeverity,
  translateSignalType,
  translateTaskStatus,
} from '../../lib/labelTranslations';
import SalesPathBar from './SalesPathBar';
import { SummarySourceLinks } from '../../components/ai/SummarySourceLinks';
import ActivityLogPanel from './ActivityLogPanel';
import CommentThread from './CommentThread';
import BuyerRelationshipMap from '../opportunities/BuyerRelationshipMap';
import OpportunityIntelligencePanel from '../intelligence/OpportunityIntelligencePanel';
import type {
  OpportunityEvent,
  ForecastAdjustment,
  DealRiskResult,
  AiSummarizeResponse,
  CloseProbabilityResult,
  ActivitySummary,
  DealRoom,
  OpportunityIntelligenceResponse,
  PipelineSuggestion,
  OpportunityFeaturesDailyLatest,
} from '../../lib/types';

const RISK_BADGE_VARIANT: Record<string, 'success' | 'warning' | 'danger'> = {
  healthy: 'success',
  at_risk: 'warning',
  high_risk: 'warning',
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
        <span className="text-xl font-bold text-slate-900 dark:text-white">{score}</span>
      </div>
    </div>
  );
}

function normalizeProbabilityPct(result: CloseProbabilityResult): number {
  const raw = result.close_probability;
  if (typeof result.close_probability_pct === 'number') return result.close_probability_pct;
  if (raw <= 1) return Math.round(raw * 100);
  return Math.round(raw);
}

function severityVariant(
  sev: string | null | undefined,
): 'success' | 'warning' | 'danger' | 'default' {
  switch (sev) {
    case 'low':
    case 'pos':
    case 'positive':
      return 'success';
    case 'high':
    case 'critical':
    case 'neg':
    case 'negative':
      return 'danger';
    case 'med':
    case 'medium':
      return 'warning';
    default:
      return 'default';
  }
}

function momentumVariant(
  band: string | null | undefined,
): 'success' | 'warning' | 'danger' | 'default' {
  switch (band) {
    case 'accelerating':
      return 'success';
    case 'steady':
      return 'default';
    case 'declining':
      return 'warning';
    case 'dead':
      return 'danger';
    default:
      return 'default';
  }
}

export default function OpportunityDetailPage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const oppId = Number(id);
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [changesOpen, setChangesOpen] = useState(false);
  const [pipelineSuggestion, setPipelineSuggestion] = useState<PipelineSuggestion | null>(null);

  useEffect(() => {
    setPipelineSuggestion(null);
  }, [oppId]);

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
      high_risk: t('opp_detail.risk_high_risk'),
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

  const { data: intelligence, isLoading: intelligenceLoading } =
    useQuery<OpportunityIntelligenceResponse>({
      queryKey: ['opportunity-intelligence', oppId],
      queryFn: () => opportunitiesApi.getIntelligence(oppId),
      enabled: !!oppId,
    });

  const opp = intelligence?.opportunity;
  const dealHealth = intelligence?.health;

  const meetingAgendaText = useMemo(() => {
    if (!opp) return '';
    const cust = opp.customer
      ? `${opp.customer.name}${opp.customer.company ? ` — ${opp.customer.company}` : ''}`
      : '-';
    const amt = opp.amount != null ? formatCurrency(opp.amount, opp.currency) : '-';
    return [
      `${t('opp_detail.agenda_deal')}: ${opp.title}`,
      `${t('opp_detail.agenda_stage')}: ${STAGE_LABELS[opp.stage as keyof typeof STAGE_LABELS] || opp.stage}`,
      `${t('opp_detail.agenda_amount')}: ${amt}`,
      `${t('opp_detail.agenda_account')}: ${cust}`,
      `${t('opp_detail.agenda_close')}: ${opp.close_date || 'TBD'}`,
      '',
      t('opp_detail.agenda_suggestion'),
    ].join('\n');
  }, [opp, STAGE_LABELS, t]);

  const copyMeetingAgenda = useCallback(async () => {
    if (!meetingAgendaText) return;
    try {
      await navigator.clipboard.writeText(meetingAgendaText);
      toast.success(t('opp_detail.meeting_agenda_copied'));
    } catch {
      toast.error(t('opp_detail.meeting_copy_failed'));
    }
  }, [meetingAgendaText, t]);
  const closePrediction = intelligence ? { data: intelligence.probability } : undefined;
  const healthLoading = intelligenceLoading;
  const closePredictionLoading = intelligenceLoading;
  const signals = intelligence?.signals ?? [];
  const tasks = intelligence?.tasks ?? [];

  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isManager = user?.role === 'manager' || user?.role === 'admin';

  const meetingPlaceholderMutation = useMutation({
    mutationFn: async () => {
      const start = new Date();
      start.setUTCDate(start.getUTCDate() + 1);
      start.setUTCHours(10, 0, 0, 0);
      return meetingsApi.schedulePlaceholder({
        title: `Meeting: ${opp?.title ?? 'Opportunity'}`,
        start_at: start.toISOString(),
        duration_minutes: 30,
        opportunity_id: oppId,
      });
    },
    onSuccess: () => {
      toast.success(t('opp_detail.meeting_placeholder_ok'));
      queryClient.invalidateQueries({ queryKey: ['activity-summary', oppId] });
    },
    onError: () => toast.error(t('opp_detail.meeting_placeholder_fail')),
  });

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

  const { data: v4LatestFeatures } = useQuery<OpportunityFeaturesDailyLatest | null>({
    queryKey: ['v4-opp-features-latest', oppId],
    queryFn: () => v4Api.getLatestOpportunityFeatures(oppId),
    enabled: !!oppId,
    retry: false,
  });

  const { data: buyerStateTimeline } = useQuery<{
    items: Array<{ snapshot_date: string; state: string; confidence: number; drivers: unknown[] }>;
    total: number;
  }>({
    queryKey: ['buyer-state-timeline', oppId],
    queryFn: () => buyerStateApi.getTimeline(oppId, 30),
    enabled: !!oppId,
    retry: false,
  });

  const { data: decisionGaps } = useQuery<{
    opportunity_id: number;
    items: Array<{
      id: number;
      gap_type: string;
      severity: string;
      recommended_actions: string[];
    }>;
    total: number;
  }>({
    queryKey: ['decision-gaps', oppId],
    queryFn: () => decisionGapsApi.listForOpportunity(oppId),
    enabled: !!oppId,
    retry: false,
  });

  const { data: benchmarkGap } = useQuery<{
    data: null | {
      segment_key: string;
      snapshot_date: string;
      gap_score: number;
      drivers: Array<{ label: string; impact: number; value?: unknown }>;
      recommended_actions: string[];
    };
  }>({
    queryKey: ['benchmarks-gap', oppId],
    queryFn: () => networkBenchmarksApi.getOpportunityGap(oppId),
    enabled: !!oppId,
    retry: false,
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

  const refreshSummaryMutation = useMutation({
    mutationFn: () =>
      aiApi.summarize({ entity_type: 'opportunity', entity_id: oppId, force: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ai-opp-summary', oppId] });
      toast.success(t('settings.operation_success'));
      setSummaryOpen(true);
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  const { data: aiChanges, isLoading: aiChangesLoading } = useQuery<AiSummarizeResponse>({
    queryKey: ['ai-opp-changes', oppId, 7],
    queryFn: () =>
      aiApi.summarizeChanges({ entity_type: 'opportunity', entity_id: oppId, days: 7 }),
    enabled: !!oppId && changesOpen,
    retry: false,
  });

  const refreshChangesMutation = useMutation({
    mutationFn: () =>
      aiApi.summarizeChanges({
        entity_type: 'opportunity',
        entity_id: oppId,
        days: 7,
        force: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ai-opp-changes', oppId, 7] });
      toast.success(t('settings.operation_success'));
      setChangesOpen(true);
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  // R6-PAGE-1 — accept canonical {items} alongside legacy {deal_rooms}.
  const { data: dealRoomsData, isLoading: dealRoomsLoading } = useQuery<{
    items?: DealRoom[];
    deal_rooms?: DealRoom[];
  }>({
    queryKey: ['deal-rooms'],
    queryFn: () => dealRoomsApi.list(),
    enabled: !!oppId,
  });

  const oppDealRooms = (dealRoomsData?.items ?? dealRoomsData?.deal_rooms ?? []).filter(
    (r) => r.opportunity_id === oppId,
  );

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
      queryClient.invalidateQueries({ queryKey: ['opportunity-intelligence', oppId] });
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  const updateTaskMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Record<string, unknown> }) =>
      aiApi.updateTask(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['opportunity-intelligence', oppId] });
      queryClient.invalidateQueries({ queryKey: ['ai-tasks'] });
      toast.success(t('settings.operation_success'));
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  const pipelineSuggestMutation = useMutation({
    mutationFn: () => aiApi.suggestPipeline({ opportunity_id: oppId }),
    onSuccess: (data) => {
      setPipelineSuggestion(data);
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  const applyPipelineStageMutation = useMutation({
    mutationFn: (stage: string) => opportunitiesApi.update(oppId, { stage }),
    onSuccess: () => {
      toast.success(t('opp_detail.pipeline_stage_applied'));
      setPipelineSuggestion(null);
      // R4-CACHE-101 — full opportunity-changed sweep so the kanban
      // card, AI cards, decision-gaps, and cockpit rollups all stay
      // in sync with the new stage.
      onOpportunityChanged(queryClient, oppId);
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  // R6-FORM-4 — Pre-R6 the only mutation on this page was the stage
  // pill. Backend ``OpportunityUpdate`` accepts 8 fields. Without an
  // edit form, reps could not rename a deal, fix amount typos, change
  // customer attribution, or mark closed_lost with a reason — every
  // such change required backend access.
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({
    title: '',
    amount: '',
    currency: '',
    close_date: '',
    status: '',
    loss_reason: '',
  });

  useEffect(() => {
    if (opp) {
      setEditForm({
        title: opp.title || '',
        amount: opp.amount != null ? String(opp.amount) : '',
        currency: opp.currency || 'TRY',
        close_date: opp.close_date || '',
        status: opp.status || '',
        loss_reason: opp.loss_reason || '',
      });
    }
  }, [opp]);

  const editMutation = useMutation({
    mutationFn: (payload: typeof editForm) => {
      const wire: Record<string, unknown> = {
        title: payload.title.trim() || undefined,
        amount: payload.amount.trim() === '' ? null : Number(payload.amount),
        currency: payload.currency || undefined,
        close_date: payload.close_date || null,
        status: payload.status || undefined,
        loss_reason: payload.loss_reason || null,
      };
      return opportunitiesApi.update(oppId, wire);
    },
    onSuccess: () => {
      toast.success('Fırsat güncellendi');
      setEditing(false);
      onOpportunityChanged(queryClient, oppId);
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
      // R4-CACHE-110 — adjustments roll up into cockpit / dashboard /
      // forecast widgets, not just this one card.
      queryClient.invalidateQueries({ queryKey: ['forecast-adjustments', oppId] });
      queryClient.invalidateQueries({ queryKey: ['cockpit'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['forecast-wow'] });
      setAdjForm({ new_amount: '', new_category: 'pipeline', reason: '' });
    },
  });

  if (intelligenceLoading) {
    return <Skeleton variant="card" count={3} />;
  }

  if (!opp) {
    return <div className="py-16 text-center text-slate-500">{t('opp_detail.not_found')}</div>;
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
          <Card
            title={t('opp_detail.card_info')}
            action={
              !editing ? (
                <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
                  Düzenle
                </Button>
              ) : (
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      setEditing(false);
                      if (opp) {
                        setEditForm({
                          title: opp.title || '',
                          amount: opp.amount != null ? String(opp.amount) : '',
                          currency: opp.currency || 'TRY',
                          close_date: opp.close_date || '',
                          status: opp.status || '',
                          loss_reason: opp.loss_reason || '',
                        });
                      }
                    }}
                  >
                    İptal
                  </Button>
                  <Button
                    size="sm"
                    loading={editMutation.isPending}
                    onClick={() => editMutation.mutate(editForm)}
                  >
                    Kaydet
                  </Button>
                </div>
              )
            }
          >
            {editing && (
              // R6-FORM-4 — inline edit form for the 6 most-changed
              // OpportunityUpdate fields. Stage stays separate (the
              // pipeline pill mutation above) so the dual-write of
              // ``stage`` plus ``previous_stage`` round-tripping
              // continues to work.
              <div className="mb-4 grid grid-cols-1 gap-3 rounded-lg border border-slate-200 bg-slate-50/60 p-3 sm:grid-cols-2 dark:border-slate-700 dark:bg-slate-800/40">
                <div className="sm:col-span-2">
                  <Input
                    label="Başlık"
                    value={editForm.title}
                    onChange={(e) => setEditForm((p) => ({ ...p, title: e.target.value }))}
                  />
                </div>
                <Input
                  label="Tutar"
                  type="number"
                  min={0}
                  step="0.01"
                  value={editForm.amount}
                  onChange={(e) => setEditForm((p) => ({ ...p, amount: e.target.value }))}
                />
                <Input
                  label="Para birimi"
                  value={editForm.currency}
                  onChange={(e) => setEditForm((p) => ({ ...p, currency: e.target.value }))}
                  placeholder="TRY"
                />
                <Input
                  label="Kapanış tarihi"
                  type="date"
                  value={editForm.close_date}
                  onChange={(e) => setEditForm((p) => ({ ...p, close_date: e.target.value }))}
                />
                <div>
                  <label className="mb-1 block text-xs text-slate-500">Durum</label>
                  <select
                    value={editForm.status}
                    onChange={(e) => setEditForm((p) => ({ ...p, status: e.target.value }))}
                    className="w-full rounded-lg border px-3 py-2 text-sm"
                    style={{
                      borderColor: 'var(--border)',
                      backgroundColor: 'var(--surface)',
                      color: 'var(--text-primary)',
                    }}
                  >
                    <option value="">— seçiniz —</option>
                    <option value="open">Açık</option>
                    <option value="closed_won">Kazanıldı</option>
                    <option value="closed_lost">Kaybedildi</option>
                  </select>
                </div>
                {editForm.status === 'closed_lost' && (
                  <div className="sm:col-span-2">
                    <Input
                      label="Kayıp nedeni"
                      value={editForm.loss_reason}
                      onChange={(e) => setEditForm((p) => ({ ...p, loss_reason: e.target.value }))}
                      placeholder="Fiyat / rakip / zamanlama / …"
                    />
                  </div>
                )}
              </div>
            )}
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t('opp_detail.lbl_stage')}
                </span>
                <p className="font-semibold text-slate-900 dark:text-white">
                  {STAGE_LABELS[opp.stage as keyof typeof STAGE_LABELS] || opp.stage}
                </p>
              </div>
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t('opp_detail.lbl_amount')}
                </span>
                <p className="font-semibold text-slate-900 dark:text-white">
                  {opp.amount != null ? formatCurrency(opp.amount, opp.currency) : '-'}
                </p>
              </div>
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t('opp_detail.lbl_close')}
                </span>
                <p className="text-slate-700 dark:text-slate-300">{opp.close_date || '-'}</p>
              </div>
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t('opp_detail.lbl_owner')}
                </span>
                <p className="text-slate-700 dark:text-slate-300">{opp.owner?.full_name || '-'}</p>
              </div>
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t('opp_detail.lbl_customer')}
                </span>
                <p className="text-slate-700 dark:text-slate-300">
                  {opp.customer ? `${opp.customer.name} (${opp.customer.company})` : '-'}
                </p>
              </div>
              {/* R5-RENDER-OPP-2 — surface lead-source attribution
                  (DB-6 / R4-TS-4). Read-only here; the channel that
                  brought the opportunity in is fixed at conversion. */}
              {opp.source && (
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    {t('opp_detail.lbl_source')}
                  </span>
                  <p className="text-slate-700 dark:text-slate-300">{opp.source}</p>
                </div>
              )}
              {/* R5-RENDER-OPP-2 — current forecast_category. The
                  adjustment form below lets managers change this; here
                  we just show the live value for context. */}
              {opp.forecast_category && (
                <div>
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    {t('opp_detail.lbl_forecast_category')}
                  </span>
                  <p className="text-slate-700 dark:text-slate-300">{opp.forecast_category}</p>
                </div>
              )}
              {/* R5-RENDER-OPP-2 — loss_reason; only meaningful when
                  the deal was marked closed_lost. */}
              {opp.status === 'closed_lost' && opp.loss_reason && (
                <div className="col-span-2">
                  <span className="text-xs text-slate-500 dark:text-slate-400">
                    {t('opp_detail.lbl_loss_reason')}
                  </span>
                  <p className="text-red-700 dark:text-red-400">{opp.loss_reason}</p>
                </div>
              )}
              <div className="col-span-2">
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t('opp_detail.lbl_rotting')}
                </span>
                <p
                  className={`font-semibold ${opp.rotting_days > 7 ? 'text-red-600' : 'text-slate-700 dark:text-slate-300'}`}
                >
                  {opp.rotting_days} {t('opp_detail.days_suffix')}
                </p>
                <p className="mt-1 text-[11px] leading-snug text-slate-500 dark:text-slate-400">
                  {t('opp_detail.rotting_hint')}
                </p>
              </div>
              {/* R5-RENDER-OPP-2 — revenue-leak audit trail. Renders a
                  compact "stage X → Y" diff when any previous_* field
                  is populated. Helps the rep see the most recent
                  slip without opening the full timeline. */}
              {(opp.previous_stage || opp.previous_amount != null || opp.previous_close_date) && (
                <div className="col-span-2 rounded-lg border border-amber-100 bg-amber-50/40 px-3 py-2 dark:border-amber-900/40 dark:bg-amber-950/20">
                  <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-700 dark:text-amber-400">
                    {t('opp_detail.recent_change')}
                  </p>
                  <div className="mt-1 space-y-0.5 text-[12px] text-slate-700 dark:text-slate-300">
                    {opp.previous_stage && opp.previous_stage !== opp.stage && (
                      <p>
                        <span className="text-slate-500 dark:text-slate-400">
                          {t('opp_detail.lbl_stage')}:
                        </span>{' '}
                        <span className="line-through opacity-60">
                          {STAGE_LABELS[opp.previous_stage as keyof typeof STAGE_LABELS] ||
                            opp.previous_stage}
                        </span>{' '}
                        →{' '}
                        <span className="font-semibold">
                          {STAGE_LABELS[opp.stage as keyof typeof STAGE_LABELS] || opp.stage}
                        </span>
                      </p>
                    )}
                    {opp.previous_amount != null && opp.previous_amount !== opp.amount && (
                      <p>
                        <span className="text-slate-500 dark:text-slate-400">
                          {t('opp_detail.lbl_amount')}:
                        </span>{' '}
                        <span className="line-through opacity-60 tabular-nums">
                          {formatCurrency(opp.previous_amount, opp.currency)}
                        </span>{' '}
                        →{' '}
                        <span className="font-semibold tabular-nums">
                          {opp.amount != null ? formatCurrency(opp.amount, opp.currency) : '-'}
                        </span>
                      </p>
                    )}
                    {opp.previous_close_date && opp.previous_close_date !== opp.close_date && (
                      <p>
                        <span className="text-slate-500 dark:text-slate-400">
                          {t('opp_detail.lbl_close')}:
                        </span>{' '}
                        <span className="line-through opacity-60 tabular-nums">
                          {opp.previous_close_date}
                        </span>{' '}
                        →{' '}
                        <span className="font-semibold tabular-nums">{opp.close_date || '-'}</span>
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </Card>

          <Card title={t('opp_detail.meeting_stub_title')}>
            <div className="space-y-3">
              <p className="text-xs text-slate-600 dark:text-slate-400">
                {t('opp_detail.meeting_stub_desc')}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => void copyMeetingAgenda()}
                >
                  <Calendar size={14} className="mr-1 inline-block align-middle" aria-hidden />
                  {t('opp_detail.meeting_copy_agenda')}
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  loading={meetingPlaceholderMutation.isPending}
                  onClick={() => meetingPlaceholderMutation.mutate()}
                >
                  {t('opp_detail.meeting_placeholder_btn')}
                </Button>
              </div>
            </div>
          </Card>

          {!['closed_won', 'closed_lost'].includes(opp.stage) && (
            <Card title={t('opp_detail.pipeline_suggest_title')}>
              <div className="space-y-3 p-1">
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  {t('opp_detail.pipeline_suggest_desc')}
                </p>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    loading={pipelineSuggestMutation.isPending}
                    onClick={() => pipelineSuggestMutation.mutate()}
                  >
                    {t('opp_detail.pipeline_suggest_btn')}
                  </Button>
                  {pipelineSuggestion &&
                    pipelineSuggestion.suggested_stage &&
                    pipelineSuggestion.suggested_stage !== opp.stage && (
                      <Button
                        type="button"
                        size="sm"
                        loading={applyPipelineStageMutation.isPending}
                        onClick={() =>
                          applyPipelineStageMutation.mutate(pipelineSuggestion.suggested_stage)
                        }
                      >
                        {t('opp_detail.pipeline_apply_btn')}
                      </Button>
                    )}
                </div>
                {pipelineSuggestion && (
                  <div className="space-y-2 border-t border-slate-100 pt-3 dark:border-slate-800">
                    <div className="flex flex-wrap items-center gap-2 text-sm">
                      <span className="text-slate-600 dark:text-slate-400">{opp.stage}</span>
                      <span className="text-slate-400">→</span>
                      <span className="font-semibold text-slate-900 dark:text-white">
                        {pipelineSuggestion.suggested_stage}
                      </span>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                        {t('opp_detail.pipeline_suggested_steps')}
                      </p>
                      <ul className="mt-1 list-inside list-disc text-sm text-slate-700 dark:text-slate-300">
                        {pipelineSuggestion.suggested_next_steps.map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ul>
                    </div>
                    {pipelineSuggestion.factors.length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-slate-500 dark:text-slate-400">
                          {t('opp_detail.pipeline_factors')}
                        </p>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {pipelineSuggestion.factors.map((f, i) => (
                            <Badge key={i} variant="info" size="sm">
                              {f}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </Card>
          )}

          {/* Related Quotes */}
          {opp.quotes && opp.quotes.length > 0 && (
            <Card title={t('opp_detail.related_quotes')}>
              <div className="space-y-2">
                {opp.quotes.map((q) => (
                  <button
                    key={q.id}
                    type="button"
                    onClick={() => navigate(`/quotes/${q.id}`)}
                    className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-4 py-3 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
                  >
                    <span className="font-mono text-sm font-semibold text-slate-900 dark:text-white">
                      {q.quote_number}
                    </span>
                    <div className="flex items-center gap-3">
                      <Badge variant="default" size="sm">
                        {q.status}
                      </Badge>
                      <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
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
              <p className="py-8 text-center text-sm text-slate-400">
                {t('opp_detail.timeline_empty')}
              </p>
            ) : (
              <div className="space-y-0">
                {events.map((event, idx) => (
                  <div
                    key={
                      event.synthetic
                        ? `syn-${event.entity_type}-${event.entity_id}-${idx}`
                        : event.id
                    }
                    className="relative flex gap-3 pb-4"
                  >
                    {/* Line */}
                    {idx < events.length - 1 && (
                      <div className="absolute left-[11px] top-6 h-full w-0.5 bg-gray-200 dark:bg-slate-800" />
                    )}
                    {/* Dot */}
                    <div className="relative z-10 mt-1 h-6 w-6 shrink-0 rounded-full bg-slate-100 flex items-center justify-center dark:bg-slate-800">
                      <div
                        className={`h-2.5 w-2.5 rounded-full ${
                          event.event_type === 'stage_change' ? 'bg-blue-500' : 'bg-gray-400'
                        }`}
                      />
                    </div>
                    {/* Content */}
                    <div className="min-w-0">
                      <p className="text-sm text-slate-900 dark:text-white">
                        {event.description || event.event_type}
                      </p>
                      <p className="text-[10px] text-slate-400">
                        {event.occurred_at ? formatDateTime(event.occurred_at) : '—'}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* V4/V5 intelligence — collapsible panel showing momentum
          drivers, similar deals, objections, and timing windows.
          Defaults closed so the page stays compact for users who
          don't need the deeper analytics; preference persists in
          sessionStorage. */}
      <div className="mt-6">
        <OpportunityIntelligencePanel opportunityId={oppId} />
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
                  <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
                    {t('opp_detail.health_score_hint')}
                  </p>
                </div>
              </div>

              {/* Indicators */}
              <div className="space-y-3">
                <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                  {t('opp_detail.indicators')}
                </h4>
                {dealHealth.indicators.map((ind) => (
                  <div key={ind.name}>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-slate-700 dark:text-slate-300">
                        {ind.label}
                      </span>
                      <span className="text-xs text-slate-500 dark:text-slate-400">
                        {ind.score}/100 ({t('opp_detail.weight')}: {ind.weight})
                      </span>
                    </div>
                    <div className="h-2 rounded-full bg-slate-100 dark:bg-slate-800">
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
                  <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">
                    {t('opp_detail.recommendations')}
                  </h4>
                  <ul className="space-y-1.5">
                    {dealHealth.recommendations.map((rec, idx) => (
                      <li
                        key={idx}
                        className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400"
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
            <p className="py-8 text-center text-sm text-slate-400">
              {t('opp_detail.health_empty')}
            </p>
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
                  <p className="mt-1 text-xs text-slate-500">{t('opp_detail.claude_evaluated')}</p>
                </div>
              </div>
              {aiRisk.factors && aiRisk.factors.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-slate-500 uppercase">
                    {t('opp_detail.risk_factors')}
                  </h4>
                  {aiRisk.factors.map((f, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded-lg bg-slate-50 dark:bg-slate-800 px-3 py-2"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900 dark:text-white">
                          {f.name}
                        </p>
                        <p className="text-xs text-slate-500 truncate">{f.description}</p>
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
                  <h4 className="text-xs font-semibold text-slate-500 uppercase mb-1">
                    {t('opp_detail.ai_suggestions')}
                  </h4>
                  <ul className="space-y-1">
                    {aiRisk.recommendations.map((r, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400"
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
            <p className="py-6 text-center text-sm text-slate-400">
              {t('opp_detail.ai_risk_empty')}
            </p>
          )}
        </Card>

        {/* Signals */}
        <Card title={t('opp_detail.indicators')}>
          {signals.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-400">
              {t('opp_detail.signals_empty')}
            </p>
          ) : (
            <div className="space-y-2">
              {signals.slice(0, 8).map((s) => (
                <div
                  key={s.id}
                  className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-slate-900 dark:text-white truncate">
                        {translateSignalType(s.signal_type, t)}
                      </p>
                      {s.evidence && (
                        <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
                          {s.evidence}
                        </p>
                      )}
                    </div>
                    <div className="shrink-0 flex items-center gap-2">
                      <Badge variant={severityVariant(s.severity)} size="sm">
                        {translateSeverity(s.severity, t)}
                      </Badge>
                      {s.is_resolved && (
                        <Badge variant="default" size="sm">
                          {t('opp_detail.signals_resolved')}
                        </Badge>
                      )}
                    </div>
                  </div>
                  {s.created_at && (
                    <p className="mt-1 text-[10px] text-slate-400">
                      {formatDateTime(s.created_at)}
                    </p>
                  )}
                </div>
              ))}
              {signals.length > 8 && (
                <p className="text-xs text-slate-400">
                  {t('opp_detail.more_suffix').replace('{count}', String(signals.length - 8))}
                </p>
              )}
            </div>
          )}
        </Card>

        {/* Daily feature snapshot */}
        <Card title={t('opp_detail.daily_snapshot')}>
          {!v4LatestFeatures ? (
            <p className="py-6 text-center text-sm text-slate-400">
              {t('opp_detail.snapshot_empty')}
            </p>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                <p className="text-[11px] text-slate-500">{t('opp_detail.snapshot_date')}</p>
                <p className="text-sm font-semibold text-slate-900 dark:text-white">
                  {formatDate(v4LatestFeatures.snapshot_date)}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                <p className="text-[11px] text-slate-500">{t('opp_detail.deal_age')}</p>
                <p className="text-sm font-semibold text-slate-900 dark:text-white">
                  {v4LatestFeatures.deal_age_days} {t('opp_detail.days_suffix')}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                <p className="text-[11px] text-slate-500">{t('opp_detail.last_rep_touch')}</p>
                <p className="text-sm font-semibold text-slate-900 dark:text-white">
                  {v4LatestFeatures.days_since_last_rep_touch} {t('opp_detail.days_suffix')}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                <p className="text-[11px] text-slate-500">{t('opp_detail.last_buyer_touch')}</p>
                <p className="text-sm font-semibold text-slate-900 dark:text-white">
                  {v4LatestFeatures.days_since_last_buyer_touch} {t('opp_detail.days_suffix')}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                <p className="text-[11px] text-slate-500">{t('opp_detail.rep_touch_14d')}</p>
                <p className="text-sm font-semibold text-slate-900 dark:text-white">
                  {v4LatestFeatures.rep_touch_count_14d}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                <p className="text-[11px] text-slate-500">{t('opp_detail.buyer_reply_14d')}</p>
                <p className="text-sm font-semibold text-slate-900 dark:text-white">
                  {v4LatestFeatures.buyer_reply_count_14d}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                <p className="text-[11px] text-slate-500">{t('opp_detail.meeting_30d')}</p>
                <p className="text-sm font-semibold text-slate-900 dark:text-white">
                  {v4LatestFeatures.meeting_count_30d}
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                <p className="text-[11px] text-slate-500">{t('opp_detail.negative_signals_14d')}</p>
                <p className="text-sm font-semibold text-slate-900 dark:text-white">
                  {v4LatestFeatures.negative_signal_count_14d}
                </p>
              </div>
              {(v4LatestFeatures.positive_signal_count_14d ?? 0) > 0 && (
                <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                  <p className="text-[11px] text-slate-500">
                    {t('opp_detail.positive_signals_14d')}
                  </p>
                  <p className="text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                    {v4LatestFeatures.positive_signal_count_14d}
                  </p>
                </div>
              )}
              {(v4LatestFeatures.quote_count ?? 0) > 0 && (
                <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                  <p className="text-[11px] text-slate-500">{t('opp_detail.quote_count')}</p>
                  <p className="text-sm font-semibold text-slate-900 dark:text-white">
                    {v4LatestFeatures.quote_count}
                  </p>
                </div>
              )}
              {v4LatestFeatures.latest_discount_pct != null && (
                <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                  <p className="text-[11px] text-slate-500">{t('opp_detail.latest_discount')}</p>
                  <p className="text-sm font-semibold text-slate-900 dark:text-white">
                    %{v4LatestFeatures.latest_discount_pct.toFixed(1)}
                  </p>
                </div>
              )}
              {(v4LatestFeatures.competitor_mentions_30d ?? 0) > 0 && (
                <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                  <p className="text-[11px] text-slate-500">
                    {t('opp_detail.competitor_mentions_30d')}
                  </p>
                  <p className="text-sm font-semibold text-amber-600 dark:text-amber-400">
                    {v4LatestFeatures.competitor_mentions_30d}
                  </p>
                </div>
              )}
              {(v4LatestFeatures.pricing_objections_30d ?? 0) > 0 && (
                <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                  <p className="text-[11px] text-slate-500">
                    {t('opp_detail.pricing_objections_30d')}
                  </p>
                  <p className="text-sm font-semibold text-amber-600 dark:text-amber-400">
                    {v4LatestFeatures.pricing_objections_30d}
                  </p>
                </div>
              )}
              {v4LatestFeatures.objection_density_norm != null && (
                <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2">
                  <p className="text-[11px] text-slate-500">{t('opp_detail.objection_density')}</p>
                  <p className="text-sm font-semibold text-slate-900 dark:text-white">
                    {v4LatestFeatures.objection_density_norm.toFixed(2)}
                  </p>
                </div>
              )}
            </div>
          )}
        </Card>

        {/* V4 Momentum */}
        <Card title={t('opp_detail.momentum')}>
          {!v4LatestFeatures?.momentum_score ? (
            <p className="py-6 text-center text-sm text-slate-400">
              {t('opp_detail.momentum_empty')}
            </p>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Badge variant={momentumVariant(v4LatestFeatures.momentum_band)} size="sm">
                    {translateMomentumBand(v4LatestFeatures.momentum_band, t)}
                  </Badge>
                  <span className="text-sm font-semibold text-slate-900 dark:text-white">
                    {t('opp_detail.score_label')}: {v4LatestFeatures.momentum_score}
                  </span>
                </div>
              </div>
              {v4LatestFeatures.momentum_drivers_json ? (
                <div className="space-y-2">
                  {(() => {
                    try {
                      const d = JSON.parse(v4LatestFeatures.momentum_drivers_json) as {
                        drivers?: Array<{ label: string; impact: number; value?: unknown }>;
                      };
                      const drivers = d.drivers ?? [];
                      return drivers.slice(0, 6).map((dr, idx) => (
                        <div
                          key={idx}
                          className="flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2"
                        >
                          <span className="text-xs text-slate-700 dark:text-slate-300">
                            {dr.label}
                          </span>
                          <Badge
                            size="sm"
                            variant={
                              dr.impact >= 5 ? 'success' : dr.impact <= -5 ? 'danger' : 'default'
                            }
                          >
                            {dr.impact > 0 ? `+${dr.impact}` : String(dr.impact)}
                          </Badge>
                        </div>
                      ));
                    } catch {
                      return (
                        <p className="text-xs text-slate-400">
                          {t('opp_detail.drivers_unparseable')}
                        </p>
                      );
                    }
                  })()}
                </div>
              ) : (
                <p className="text-xs text-slate-400">{t('opp_detail.drivers_empty')}</p>
              )}
            </div>
          )}
        </Card>

        {/* Buyer State Timeline */}
        <Card title={t('opp_detail.buyer_state')}>
          {buyerStateTimeline?.items?.length ? (
            <div className="space-y-2">
              {buyerStateTimeline.items.slice(0, 10).map((it) => {
                // `drivers[]` is the *reason* the buyer was classified
                // engaged/stalling/etc. Previously fetched then dropped
                // (audit F-6). Backend ships them as opaque objects so
                // we narrow defensively.
                const drivers = Array.isArray((it as { drivers?: unknown }).drivers)
                  ? (it as { drivers: unknown[] }).drivers
                      .map((d) =>
                        typeof d === 'string'
                          ? d
                          : typeof d === 'object' && d !== null && 'label' in d
                            ? String((d as { label: unknown }).label)
                            : null,
                      )
                      .filter((s): s is string => Boolean(s))
                  : [];
                return (
                  <div
                    key={it.snapshot_date}
                    className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-slate-900 dark:text-white">
                        {translateBuyerState(it.state, t)}
                        <span className="ml-2 text-xs text-slate-400">
                          {(it.confidence * 100).toFixed(0)}%
                        </span>
                      </p>
                      <p className="text-[11px] text-slate-500">{formatDate(it.snapshot_date)}</p>
                      {drivers.length > 0 && (
                        <ul className="mt-1 flex flex-wrap gap-1">
                          {drivers.slice(0, 3).map((d, i) => (
                            <li
                              key={i}
                              className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                            >
                              {d}
                            </li>
                          ))}
                          {drivers.length > 3 && (
                            <li className="rounded-md bg-slate-50 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                              +{drivers.length - 3}
                            </li>
                          )}
                        </ul>
                      )}
                    </div>
                    <Badge variant={it.state === 'stalling' ? 'warning' : 'default'} size="sm">
                      {translateBuyerState(it.state, t)}
                    </Badge>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-slate-400">
              {t('opp_detail.buyer_state_empty')}
            </p>
          )}
        </Card>

        {/* Decision Gaps */}
        <Card title={t('opp_detail.decision_gaps')}>
          {decisionGaps?.items?.length ? (
            <div className="space-y-2">
              {decisionGaps.items.slice(0, 8).map((g) => (
                <div
                  key={g.id}
                  className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-900 dark:text-white">
                      {translateGapType(g.gap_type, t)}
                    </p>
                    {((g.recommended_actions ?? []) as string[]).length > 0 && (
                      <ul className="mt-1 flex flex-wrap gap-1">
                        {((g.recommended_actions ?? []) as string[])
                          .slice(0, 4)
                          .map((action, i) => (
                            <li
                              key={i}
                              className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                            >
                              {action}
                            </li>
                          ))}
                        {((g.recommended_actions ?? []) as string[]).length > 4 && (
                          <li className="rounded-md bg-slate-50 px-1.5 py-0.5 text-[11px] text-slate-500 dark:bg-slate-900 dark:text-slate-400">
                            +{((g.recommended_actions ?? []) as string[]).length - 4}
                          </li>
                        )}
                      </ul>
                    )}
                  </div>
                  <Badge variant={severityVariant(g.severity)} size="sm">
                    {translateSeverity(g.severity, t)}
                  </Badge>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-slate-400">
              {t('opp_detail.decision_gaps_empty')}
            </p>
          )}
        </Card>

        {/* Segment Benchmark Gap */}
        <Card title={t('opp_detail.benchmark_gap_title')}>
          {benchmarkGap?.data ? (
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <Badge
                  variant={
                    benchmarkGap.data.gap_score >= 65
                      ? 'success'
                      : benchmarkGap.data.gap_score >= 45
                        ? 'warning'
                        : 'danger'
                  }
                  size="sm"
                >
                  {t('opp_detail.benchmark_gap_score')}: {benchmarkGap.data.gap_score}
                </Badge>
                <span className="text-xs text-slate-400">{benchmarkGap.data.segment_key}</span>
              </div>
              {benchmarkGap.data.recommended_actions?.[0] && (
                <p className="text-sm text-slate-700 dark:text-slate-300">
                  {benchmarkGap.data.recommended_actions[0]}
                </p>
              )}
              {benchmarkGap.data.drivers?.length ? (
                <div className="space-y-2">
                  {benchmarkGap.data.drivers.slice(0, 4).map((d, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2"
                    >
                      <span className="text-xs text-slate-700 dark:text-slate-300">{d.label}</span>
                      <Badge
                        size="sm"
                        variant={d.impact > 0 ? 'success' : d.impact < 0 ? 'danger' : 'default'}
                      >
                        {d.impact > 0 ? `+${d.impact}` : String(d.impact)}
                      </Badge>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400">{t('opp_detail.benchmark_drivers_empty')}</p>
              )}
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-slate-400">
              {t('opp_detail.benchmark_empty')}
            </p>
          )}
        </Card>

        {/* Close Probability */}
        <Card title={t('opp_detail.close_probability')}>
          {closePredictionLoading ? (
            <Skeleton variant="card" />
          ) : closePrediction?.data ? (
            <div className="space-y-4">
              {(() => {
                const pct = normalizeProbabilityPct(closePrediction.data);
                const stageProb = opp.probability ?? 0;
                const stagePct =
                  stageProb <= 1 ? Math.round(stageProb * 100) : Math.round(stageProb);
                const delta = pct - stagePct;
                return (
                  <>
                    <div className="flex items-center gap-4">
                      <ScoreRing score={pct} />
                      <div className="flex-1">
                        <div className="flex items-center justify-between">
                          <Badge
                            variant={
                              (closePrediction.data.confidence_band ??
                                closePrediction.data.confidence) === 'high'
                                ? 'success'
                                : (closePrediction.data.confidence_band ??
                                      closePrediction.data.confidence) === 'medium'
                                  ? 'warning'
                                  : 'danger'
                            }
                          >
                            {(closePrediction.data.confidence_band ??
                              closePrediction.data.confidence) === 'high'
                              ? t('opp_detail.conf_high')
                              : (closePrediction.data.confidence_band ??
                                    closePrediction.data.confidence) === 'medium'
                                ? t('opp_detail.conf_medium')
                                : t('opp_detail.conf_low')}
                          </Badge>
                          <div className="text-xs text-slate-500 dark:text-slate-400">
                            {t('opp_detail.stage_probability')}:{' '}
                            <span className="font-semibold">{stagePct}%</span>{' '}
                            <span className={delta >= 0 ? 'text-green-600' : 'text-red-600'}>
                              ({delta >= 0 ? '+' : ''}
                              {delta}%)
                            </span>
                          </div>
                        </div>

                        <div className="mt-2 h-2 rounded-full bg-slate-100 dark:bg-slate-800">
                          <div
                            className="h-2 rounded-full bg-blue-600 transition-all duration-700"
                            style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
                          />
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          {t('opp_detail.close_prob_hint')}
                        </p>
                      </div>
                    </div>
                  </>
                );
              })()}
              {closePrediction.data.factors && closePrediction.data.factors.length > 0 && (
                <div className="space-y-2">
                  <h4 className="text-xs font-semibold text-slate-500 uppercase">
                    {t('opp_detail.influencing_factors')}
                  </h4>
                  {closePrediction.data.factors.map((f, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded-lg bg-slate-50 dark:bg-slate-800 px-3 py-2"
                    >
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-slate-900 dark:text-white">
                          {f.name || f.label || '-'}
                        </p>
                        <p className="text-xs text-slate-500 truncate">{f.evidence}</p>
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
                  <h4 className="text-xs font-semibold text-slate-500 uppercase mb-1">
                    {t('opp_detail.next_steps')}
                  </h4>
                  <ul className="space-y-1">
                    {closePrediction.data.next_steps.map((step, i) => (
                      <li
                        key={i}
                        className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400"
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
            <p className="py-6 text-center text-sm text-slate-400">
              {t('opp_detail.close_data_empty')}
            </p>
          )}
        </Card>

        {/* AI Summary */}
        <Card
          title={t('opp_detail.ai_summary')}
          action={
            <>
              <Button size="sm" variant="secondary" onClick={() => setSummaryOpen((s) => !s)}>
                {summaryOpen ? t('opp_detail.ai_summary_close') : t('opp_detail.ai_summary_open')}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                loading={refreshSummaryMutation.isPending}
                onClick={() => refreshSummaryMutation.mutate()}
              >
                {t('opp_detail.ai_summary_refresh')}
              </Button>
            </>
          }
        >
          {aiSummaryLoading ? (
            <Skeleton variant="card" />
          ) : aiSummary && summaryOpen ? (
            <div className="space-y-3">
              <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-relaxed">
                {aiSummary.summary}
              </p>
              {aiSummary.sources && aiSummary.sources.length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                    {t('opp_detail.sources')}
                  </p>
                  <SummarySourceLinks sources={aiSummary.sources} />
                </div>
              )}
              {aiSummary.generated_at && (
                <p className="text-[10px] text-slate-400">
                  {formatDateTime(aiSummary.generated_at)}
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
            <p className="py-6 text-center text-sm text-slate-400">
              {summaryOpen ? t('opp_detail.ai_summary_empty') : t('opp_detail.ai_summary_open')}
            </p>
          )}
        </Card>

        <Card
          title={t('opp_detail.changes_title').replace('{{d}}', '7')}
          action={
            <div className="flex flex-wrap gap-2">
              <Button size="sm" variant="secondary" onClick={() => setChangesOpen((s) => !s)}>
                {changesOpen ? t('opp_detail.ai_summary_close') : t('opp_detail.changes_show')}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                loading={refreshChangesMutation.isPending}
                disabled={!changesOpen}
                onClick={() => refreshChangesMutation.mutate()}
              >
                {t('opp_detail.changes_refresh')}
              </Button>
            </div>
          }
        >
          {aiChangesLoading ? (
            <Skeleton variant="card" />
          ) : aiChanges && changesOpen ? (
            <div className="space-y-3">
              <p className="text-sm text-slate-700 dark:text-slate-300 whitespace-pre-wrap leading-relaxed">
                {aiChanges.summary}
              </p>
              {aiChanges.sources && aiChanges.sources.length > 0 && (
                <div className="space-y-1">
                  <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">
                    {t('opp_detail.sources')}
                  </p>
                  <SummarySourceLinks sources={aiChanges.sources} />
                </div>
              )}
              {aiChanges.generated_at && (
                <p className="text-[10px] text-slate-400">
                  {formatDateTime(aiChanges.generated_at)}
                </p>
              )}
              {aiChanges.cached && (
                <Badge variant="default" size="sm">
                  {t('opp_detail.cached')}
                </Badge>
              )}
            </div>
          ) : (
            <p className="py-6 text-center text-sm text-slate-400">
              {changesOpen ? t('opp_detail.ai_summary_empty') : t('opp_detail.changes_hint')}
            </p>
          )}
        </Card>
      </div>

      {/* Tasks */}
      <div className="mt-6">
        <Card title={t('opp_detail.tasks_card_title')}>
          {tasks.length === 0 ? (
            <p className="py-6 text-center text-sm text-slate-400">{t('opp_detail.tasks_empty')}</p>
          ) : (
            <div className="space-y-2">
              {tasks.slice(0, 12).map((task) => {
                const isDone = task.status !== 'open';
                return (
                  <div
                    key={task.id}
                    className="flex items-start justify-between gap-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p
                        className={`text-sm font-semibold ${
                          isDone ? 'text-slate-400 line-through' : 'text-slate-900 dark:text-white'
                        }`}
                      >
                        {task.title}
                      </p>
                      {task.description && (
                        <p className="text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
                          {task.description}
                        </p>
                      )}
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-slate-400">
                        {task.due_at && (
                          <span>
                            {t('opp_detail.task_due_label')}: {formatDate(task.due_at)}
                          </span>
                        )}
                        {task.source && (
                          <span>
                            {t('opp_detail.task_source_label')}: {task.source}
                          </span>
                        )}
                        {task.priority && (
                          <span>
                            {t('opp_detail.task_priority_label')}: {task.priority}
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="shrink-0 flex items-center gap-2">
                      <Badge variant={isDone ? 'default' : 'warning'} size="sm">
                        {translateTaskStatus(task.status, t)}
                      </Badge>
                      {!isDone && (
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={updateTaskMutation.isPending}
                          onClick={() =>
                            updateTaskMutation.mutate({
                              id: task.id,
                              payload: { status: 'done' },
                            })
                          }
                        >
                          {t('opp_detail.task_complete')}
                        </Button>
                      )}
                    </div>
                  </div>
                );
              })}
              {tasks.length > 12 && (
                <p className="text-xs text-slate-400">
                  {t('opp_detail.more_suffix').replace('{count}', String(tasks.length - 12))}
                </p>
              )}
            </div>
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
                      <tr className="border-b border-slate-200 dark:border-slate-800">
                        <th className="py-2 px-3 text-left text-xs text-slate-500">
                          {t('opp_detail.tbl_date')}
                        </th>
                        <th className="py-2 px-3 text-right text-xs text-slate-500">
                          {t('opp_detail.tbl_orig_amount')}
                        </th>
                        <th className="py-2 px-3 text-right text-xs text-slate-500">
                          {t('opp_detail.tbl_new_amount')}
                        </th>
                        <th className="py-2 px-3 text-left text-xs text-slate-500">
                          {t('opp_detail.tbl_category')}
                        </th>
                        <th className="py-2 px-3 text-left text-xs text-slate-500">
                          {t('opp_detail.tbl_reason')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {adjustmentsData.adjustments.map((adj) => (
                        <tr key={adj.id} className="border-b border-gray-50 dark:border-slate-800">
                          <td className="py-2 px-3 text-xs text-slate-600 dark:text-slate-400">
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
                          <td className="py-2 px-3 text-xs text-slate-500 dark:text-slate-400 max-w-[200px] truncate">
                            {adj.reason || '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="py-4 text-center text-sm text-slate-400">
                  {t('opp_detail.adj_none')}
                </p>
              )}

              {/* Adjustment form (manager only) */}
              {isManager && (
                <div className="border-t border-slate-100 dark:border-slate-800 pt-4">
                  <h4 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">
                    {t('opp_detail.new_adj')}
                  </h4>
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
                        {t('opp_detail.lbl_new_amount')}
                      </label>
                      <input
                        type="number"
                        value={adjForm.new_amount}
                        onChange={(e) => setAdjForm((f) => ({ ...f, new_amount: e.target.value }))}
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white"
                        placeholder="0.00"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
                        {t('opp_detail.lbl_category')}
                      </label>
                      <select
                        value={adjForm.new_category}
                        onChange={(e) =>
                          setAdjForm((f) => ({ ...f, new_category: e.target.value }))
                        }
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white"
                      >
                        {FORECAST_CATEGORIES.map((cat) => (
                          <option key={cat.value} value={cat.value}>
                            {cat.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="block text-xs text-slate-500 dark:text-slate-400 mb-1">
                        {t('opp_detail.lbl_reason')}
                      </label>
                      <textarea
                        value={adjForm.reason}
                        onChange={(e) => setAdjForm((f) => ({ ...f, reason: e.target.value }))}
                        rows={1}
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white"
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
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t('opp_detail.total_activities')}
                </span>
                <p className="text-xl font-bold text-slate-900 dark:text-white">
                  {activitySummary.total_activities}
                </p>
              </div>
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t('opp_detail.since_last')}
                </span>
                <p
                  className={`text-xl font-bold ${activitySummary.days_since_last_activity > 7 ? 'text-red-600' : 'text-slate-900 dark:text-white'}`}
                >
                  {activitySummary.days_since_last_activity} {t('opp_detail.days_suffix')}
                </p>
              </div>
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t('opp_detail.avg_stage')}
                </span>
                <p className="text-xl font-bold text-slate-900 dark:text-white">
                  {activitySummary.avg_activities_for_stage}
                </p>
              </div>
              <div>
                <span className="text-xs text-slate-500 dark:text-slate-400">
                  {t('opp_detail.by_type')}
                </span>
                <div className="mt-1 flex flex-wrap gap-1">
                  {Object.entries(activitySummary.by_type).map(([type, count]) => (
                    <Badge key={type} variant="default" size="sm">
                      {translateActivityType(type, t)}: {count}
                    </Badge>
                  ))}
                  {Object.keys(activitySummary.by_type).length === 0 && (
                    <span className="text-xs text-slate-400">-</span>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <p className="py-4 text-center text-sm text-slate-400">
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
                  className="flex w-full items-center justify-between rounded-lg border border-slate-200 px-4 py-3 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-800"
                >
                  <span className="text-sm font-semibold text-slate-900 dark:text-white">
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
              <p className="mb-3 text-sm text-slate-400">{t('opp_detail.dr_empty')}</p>
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
