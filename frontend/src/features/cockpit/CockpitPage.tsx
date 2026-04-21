import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, ResponsiveContainer } from 'recharts';
import {
  AlertTriangle,
  TrendingUp,
  Clock,
  Bot,
  Activity,
  CheckCircle2,
  Play,
  XCircle,
  Swords,
  ShieldAlert,
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import {
  cockpitApi,
  playbookApi,
  coachingApi,
  aiApi,
  dealHealthApi,
  analyticsApi,
} from '../../lib/api';
import { formatCurrency, formatDate, formatDateTime } from '../../lib/formatters';
import { useAuthStore } from '../../stores/authStore';
import { useT } from '../../hooks/useT';

import type {
  CockpitKpis,
  RevenueSignalItem,
  CockpitAction,
  CoachingOverview,
  ActivityDroughtItem,
  RevenueLeakResult,
  RevenueLeakItem,
} from '../../lib/types';

// ── Severity / priority color helpers ────────────────

type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'default';

const SEVERITY_VARIANT: Record<string, BadgeVariant> = {
  critical: 'danger',
  high: 'warning',
  medium: 'warning',
  low: 'default',
};

const PRIORITY_VARIANT: Record<string, BadgeVariant> = {
  urgent: 'danger',
  high: 'warning',
  normal: 'info',
  low: 'default',
};

// ── KPI Strip ────────────────────────────────────────

function KpiStrip({ data, isLoading }: { data?: CockpitKpis; isLoading: boolean }) {
  const t = useT();

  const kpis = useMemo(() => {
    if (!data) return [];
    return [
      {
        label: t('cockpit.kpi_pipeline'),
        value: formatCurrency(data.pipeline_total, data.pipeline_currency),
        icon: <TrendingUp size={18} className="text-blue-500" />,
      },
      {
        label: t('cockpit.kpi_win_rate'),
        value: `%${(data.win_rate * 100).toFixed(1)}`,
        icon: <CheckCircle2 size={18} className="text-green-500" />,
      },
      {
        label: t('cockpit.kpi_at_risk'),
        value: String(data.at_risk_count),
        icon: <AlertTriangle size={18} className="text-red-500" />,
      },
      {
        label: t('cockpit.kpi_avg_velocity'),
        value: String(data.avg_deal_velocity_days),
        icon: <Clock size={18} className="text-amber-500" />,
      },
      {
        label: t('cockpit.kpi_ai_tasks'),
        value: String(data.open_ai_tasks),
        icon: <Bot size={18} className="text-purple-500" />,
      },
      {
        label: t('cockpit.kpi_signals'),
        value: String(data.signal_stats.total),
        icon: <Activity size={18} className="text-indigo-500" />,
      },
    ];
  }, [data, t]);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-xl" />
        ))}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
      {kpis.map((kpi) => (
        <div key={kpi.label} className="card-modern flex flex-col gap-2 px-5 py-4">
          <div className="flex items-center gap-2 text-xs font-medium text-gray-500 dark:text-gray-400">
            {kpi.icon}
            {kpi.label}
          </div>
          <span className="text-xl font-bold text-gray-900 dark:text-white">{kpi.value}</span>
        </div>
      ))}
    </div>
  );
}

// ── Signal Stream ────────────────────────────────────

function SignalStream() {
  const t = useT();
  const severityLabel = useMemo(
    () => ({
      critical: t('cockpit.severity_critical'),
      high: t('cockpit.severity_high'),
      medium: t('cockpit.severity_medium'),
      low: t('cockpit.severity_low'),
    }),
    [t],
  );
  const [severityFilter, setSeverityFilter] = useState<string>('all');
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['cockpit', 'signals', severityFilter],
    queryFn: () =>
      cockpitApi.getSignals(severityFilter !== 'all' ? { severity: severityFilter } : undefined),
    refetchInterval: 30_000,
  });

  const resolveMutation = useMutation({
    mutationFn: cockpitApi.resolveSignal,
    onSuccess: () => {
      toast.success(t('cockpit.toast_signal_resolved'));
      queryClient.invalidateQueries({ queryKey: ['cockpit'] });
    },
  });

  const signals: RevenueSignalItem[] = data?.items ?? [];

  return (
    <Card
      title={t('cockpit.signal_stream_title')}
      action={
        <select
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
        >
          <option value="all">{t('cockpit.filter_all')}</option>
          <option value="critical">{t('cockpit.severity_critical')}</option>
          <option value="high">{t('cockpit.severity_high')}</option>
          <option value="medium">{t('cockpit.severity_medium')}</option>
          <option value="low">{t('cockpit.severity_low')}</option>
        </select>
      }
    >
      {isLoading ? (
        <Skeleton variant="line" count={5} />
      ) : signals.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">{t('cockpit.signal_empty')}</p>
      ) : (
        <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1">
          {signals.map((signal) => (
            <div
              key={signal.id}
              className="flex items-start justify-between gap-3 rounded-lg border border-gray-100 p-3 dark:border-gray-700"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Badge variant={SEVERITY_VARIANT[signal.severity] ?? 'default'} size="sm">
                    {severityLabel[signal.severity as keyof typeof severityLabel] ??
                      signal.severity}
                  </Badge>
                  <span className="text-xs text-gray-400">{signal.signal_type}</span>
                </div>
                {signal.recommended_action && (
                  <p className="mt-1 text-sm text-gray-700 dark:text-gray-300">
                    {signal.recommended_action}
                  </p>
                )}
                <p className="mt-1 text-xs text-gray-400">{formatDateTime(signal.created_at)}</p>
              </div>
              {!signal.is_resolved && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => resolveMutation.mutate(signal.id)}
                  loading={resolveMutation.isPending}
                  title={t('cockpit.resolve_title')}
                >
                  <CheckCircle2 size={16} />
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ── Action Queue ─────────────────────────────────────

function ActionQueue() {
  const t = useT();
  const priorityLabel = useMemo(
    () => ({
      urgent: t('cockpit.priority_urgent'),
      high: t('cockpit.priority_high'),
      normal: t('cockpit.priority_normal'),
      low: t('cockpit.priority_low'),
    }),
    [t],
  );
  const { data, isLoading } = useQuery({
    queryKey: ['cockpit', 'actions'],
    queryFn: cockpitApi.getActions,
    refetchInterval: 60_000,
  });

  const actions: CockpitAction[] = data?.items ?? [];

  return (
    <Card title={t('cockpit.ai_tasks_card')}>
      {isLoading ? (
        <Skeleton variant="line" count={4} />
      ) : actions.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">{t('cockpit.no_pending_tasks')}</p>
      ) : (
        <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1">
          {actions.map((action) => (
            <div
              key={action.id}
              className="rounded-lg border border-gray-100 p-3 dark:border-gray-700"
            >
              <div className="flex items-center gap-2">
                <Badge variant={PRIORITY_VARIANT[action.priority] ?? 'default'} size="sm">
                  {priorityLabel[action.priority as keyof typeof priorityLabel] ?? action.priority}
                </Badge>
              </div>
              <p className="mt-1 text-sm font-medium text-gray-800 dark:text-gray-200">
                {action.title}
              </p>
              {action.description && (
                <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
                  {action.description}
                </p>
              )}
              {action.due_at && (
                <p className="mt-1 text-xs text-gray-400">
                  {t('cockpit.due_prefix')} {formatDate(action.due_at)}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ── Trend Charts ─────────────────────────────────────

function TrendCharts() {
  const t = useT();
  const { data, isLoading } = useQuery({
    queryKey: ['cockpit', 'trends'],
    queryFn: cockpitApi.getTrends,
  });

  const chartData: { week: string; signal_count: number }[] = data?.signal_volume ?? [];

  return (
    <Card title={t('cockpit.trend_title')}>
      {isLoading ? (
        <Skeleton className="h-64 rounded-xl" />
      ) : chartData.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">{t('cockpit.no_trend')}</p>
      ) : (
        <ResponsiveContainer width="100%" height={280}>
          <BarChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis dataKey="week" tick={{ fontSize: 12 }} />
            <YAxis tick={{ fontSize: 12 }} allowDecimals={false} />
            <Tooltip
              contentStyle={{
                borderRadius: 8,
                fontSize: 13,
                border: '1px solid #e5e7eb',
              }}
            />
            <Bar
              dataKey="signal_count"
              name={t('cockpit.chart_signal_count')}
              fill="#ef4444"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

// ── Playbook Panel ───────────────────────────────────

interface PlaybookExecution {
  id: number;
  playbook_name: string;
  status: string;
  started_at: string;
  opportunity_id: number | null;
}

function PlaybookPanel() {
  const t = useT();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['playbook', 'executions'],
    queryFn: () => playbookApi.getExecutions({ status: 'running' }),
    refetchInterval: 60_000,
  });

  const cancelMutation = useMutation({
    mutationFn: playbookApi.cancelExecution,
    onSuccess: () => {
      toast.success(t('cockpit.toast_playbook_cancelled'));
      queryClient.invalidateQueries({ queryKey: ['playbook'] });
    },
  });

  const executions: PlaybookExecution[] = data?.items ?? data ?? [];

  return (
    <Card title={t('cockpit.playbooks_active')}>
      {isLoading ? (
        <Skeleton variant="line" count={3} />
      ) : executions.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">{t('cockpit.no_active_playbook')}</p>
      ) : (
        <div className="space-y-2">
          {executions.map((exec) => (
            <div
              key={exec.id}
              className="flex items-center justify-between rounded-lg border border-gray-100 px-4 py-3 dark:border-gray-700"
            >
              <div className="flex items-center gap-3">
                <Play size={16} className="text-green-500" />
                <div>
                  <p className="text-sm font-medium text-gray-800 dark:text-gray-200">
                    {exec.playbook_name}
                  </p>
                  <p className="text-xs text-gray-400">{formatDateTime(exec.started_at)}</p>
                </div>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => cancelMutation.mutate(exec.id)}
                loading={cancelMutation.isPending}
                title={t('cockpit.cancel_title')}
              >
                <XCircle size={16} className="text-red-400" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ── Coaching Panel (manager only) ────────────────────

function CoachingPanel() {
  const t = useT();
  const { data, isLoading } = useQuery<CoachingOverview>({
    queryKey: ['coaching', 'overview'],
    queryFn: coachingApi.getOverview,
    refetchInterval: 120_000,
  });

  const riskVariant = (level: string): BadgeVariant => {
    if (level === 'high' || level === 'critical') return 'danger';
    if (level === 'medium') return 'warning';
    return 'success';
  };

  return (
    <Card title={t('cockpit.coaching_title')}>
      {isLoading ? (
        <Skeleton variant="table" />
      ) : !data || data.reps.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">{t('cockpit.data_not_found')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-gray-200 dark:border-gray-700">
                <th className="pb-2 font-medium text-gray-500 dark:text-gray-400">
                  {t('cockpit.col_rep')}
                </th>
                <th className="pb-2 font-medium text-gray-500 dark:text-gray-400">
                  {t('cockpit.col_score')}
                </th>
                <th className="pb-2 font-medium text-gray-500 dark:text-gray-400">
                  {t('cockpit.col_risk')}
                </th>
                <th className="pb-2 font-medium text-gray-500 dark:text-gray-400">
                  {t('cockpit.col_recommendations')}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.reps.map((rep) => (
                <tr
                  key={rep.user_id}
                  className="border-b border-gray-100 last:border-0 dark:border-gray-700"
                >
                  <td className="py-2 font-medium text-gray-800 dark:text-gray-200">
                    {rep.user_name}
                  </td>
                  <td className="py-2 text-gray-700 dark:text-gray-300">{rep.score.toFixed(0)}</td>
                  <td className="py-2">
                    <Badge variant={riskVariant(rep.risk_level)} size="sm">
                      {rep.risk_level}
                    </Badge>
                  </td>
                  <td className="py-2 text-xs text-gray-500 dark:text-gray-400">
                    {rep.recommendations.slice(0, 2).join('; ')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ── Competitive Intel Panel ─────────────────────────

function CompetitiveIntelPanel() {
  const t = useT();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['ai-competitive-intel'],
    queryFn: () => aiApi.competitiveIntel(90),
    retry: false,
  });

  const crawlMutation = useMutation({
    mutationFn: aiApi.crawlCompetitors,
    onSuccess: () => {
      toast.success(t('cockpit.toast_crawl_ok'));
      queryClient.invalidateQueries({ queryKey: ['ai-competitive-intel'] });
    },
    onError: () => {
      toast.error(t('cockpit.toast_crawl_fail'));
    },
  });

  const competitors = data?.competitors ?? data?.by_competitor ?? [];

  return (
    <Card
      title={t('cockpit.competitive_title')}
      action={
        <Button
          variant="secondary"
          size="sm"
          onClick={() => crawlMutation.mutate()}
          loading={crawlMutation.isPending}
        >
          {t('cockpit.crawl_btn')}
        </Button>
      }
    >
      {isLoading ? (
        <Skeleton variant="line" count={3} />
      ) : competitors.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">{t('cockpit.no_comp_mentions')}</p>
      ) : (
        <div className="space-y-3">
          {competitors
            .slice(0, 5)
            .map(
              (comp: {
                name?: string;
                competitor?: string;
                mention_count: number;
                sentiment_avg?: number;
                recent_mentions?: { source_type: string; context_snippet: string }[];
              }) => {
                const compName = comp.name ?? comp.competitor ?? t('cockpit.unknown');
                return (
                  <div
                    key={compName}
                    className="rounded-lg border border-gray-100 dark:border-gray-700 px-4 py-3"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <Swords size={14} className="text-red-400" />
                        <span className="text-sm font-semibold text-gray-900 dark:text-white">
                          {compName}
                        </span>
                      </div>
                      <Badge variant={comp.mention_count > 5 ? 'danger' : 'info'} size="sm">
                        {t('cockpit.mentions_count').replace('{count}', String(comp.mention_count))}
                      </Badge>
                    </div>
                    {comp.sentiment_avg != null && (
                      <p className="text-xs text-gray-500 mb-1">
                        {t('cockpit.sentiment')}{' '}
                        {comp.sentiment_avg > 0
                          ? t('cockpit.sentiment_positive')
                          : comp.sentiment_avg < 0
                            ? t('cockpit.sentiment_negative')
                            : t('cockpit.sentiment_neutral')}
                      </p>
                    )}
                    {comp.recent_mentions?.slice(0, 1).map((m, i) => (
                      <p key={i} className="text-xs text-gray-400 truncate">
                        [{m.source_type}] {m.context_snippet}
                      </p>
                    ))}
                  </div>
                );
              },
            )}
        </div>
      )}
    </Card>
  );
}

// ── At-Risk Deals Panel ─────────────────────────────

function AtRiskDealsPanel() {
  const t = useT();
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ['deal-health-at-risk-cockpit'],
    queryFn: () => dealHealthApi.getAtRisk(40),
    refetchInterval: 120_000,
  });

  const deals = data?.opportunities ?? data?.deals ?? data?.items ?? [];

  return (
    <Card title={t('cockpit.at_risk_title')}>
      {isLoading ? (
        <Skeleton variant="line" count={3} />
      ) : deals.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">{t('cockpit.no_at_risk')}</p>
      ) : (
        <div className="space-y-2">
          {deals
            .slice(0, 5)
            .map(
              (deal: {
                opportunity_id: number;
                title: string;
                score: number;
                risk_level: string;
              }) => (
                <button
                  key={deal.opportunity_id}
                  type="button"
                  onClick={() => navigate(`/opportunities/${deal.opportunity_id}`)}
                  className="flex w-full items-center justify-between rounded-lg border border-gray-100 dark:border-gray-700 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <ShieldAlert
                      size={14}
                      className={deal.score < 30 ? 'text-red-500' : 'text-amber-500'}
                    />
                    <span className="text-sm font-medium text-gray-900 dark:text-white truncate">
                      {deal.title}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`text-sm font-bold ${deal.score < 30 ? 'text-red-600' : 'text-amber-600'}`}
                    >
                      {deal.score}
                    </span>
                    <Badge
                      variant={deal.risk_level === 'critical' ? 'danger' : 'warning'}
                      size="sm"
                    >
                      {deal.risk_level === 'critical'
                        ? t('cockpit.badge_critical')
                        : t('cockpit.badge_risk')}
                    </Badge>
                  </div>
                </button>
              ),
            )}
        </div>
      )}
    </Card>
  );
}

// ── Activity Drought Panel (Modul 6) ──────────────────

function ActivityDroughtPanel() {
  const t = useT();
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ['activity-drought'],
    queryFn: () => analyticsApi.getActivityDrought(7),
    refetchInterval: 120_000,
  });

  const items: ActivityDroughtItem[] = data?.items ?? [];

  const stageLabels = useMemo(
    () => ({
      prospecting: t('opp_detail.stage_prospecting'),
      qualified: t('opp_detail.stage_qualified'),
      proposal: t('opp_detail.stage_proposal'),
      negotiation: t('opp_detail.stage_negotiation'),
    }),
    [t],
  );

  return (
    <Card title={t('cockpit.activity_drought')}>
      {isLoading ? (
        <Skeleton variant="line" count={3} />
      ) : items.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">{t('cockpit.no_drought')}</p>
      ) : (
        <div className="space-y-2">
          {items.slice(0, 7).map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => navigate(`/opportunities/${item.id}`)}
              className="flex w-full items-center justify-between rounded-lg border border-gray-100 dark:border-gray-700 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
            >
              <div className="flex items-center gap-2 min-w-0">
                <Clock
                  size={14}
                  className={item.days_since_last > 14 ? 'text-red-500' : 'text-amber-500'}
                />
                <div className="min-w-0 text-left">
                  <span className="text-sm font-medium text-gray-900 dark:text-white truncate block">
                    {item.title}
                  </span>
                  <span className="text-xs text-gray-400">
                    {item.owner_name} -{' '}
                    {stageLabels[item.stage as keyof typeof stageLabels] || item.stage}
                  </span>
                </div>
              </div>
              <Badge variant={item.days_since_last > 14 ? 'danger' : 'warning'} size="sm">
                {t('cockpit.days_count').replace('{days}', String(item.days_since_last))}
              </Badge>
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}

// ── Revenue Leak Panel (Modul 10) ───────────────────

function RevenueLeakPanel() {
  const t = useT();
  const navigate = useNavigate();
  const { data: leaksRaw, isLoading } = useQuery({
    queryKey: ['revenue-leaks-cockpit'],
    queryFn: () => analyticsApi.getRevenueLeaks(),
    refetchInterval: 120_000,
  });

  const leaks: RevenueLeakResult | undefined = leaksRaw?.data;

  const stageLabels = useMemo(
    () => ({
      prospecting: t('opp_detail.stage_prospecting'),
      qualified: t('opp_detail.stage_qualified'),
      proposal: t('opp_detail.stage_proposal'),
      negotiation: t('opp_detail.stage_negotiation'),
    }),
    [t],
  );

  return (
    <Card title={t('cockpit.revenue_leak')}>
      {isLoading ? (
        <Skeleton variant="line" count={3} />
      ) : !leaks || leaks.items.length === 0 ? (
        <p className="py-6 text-center text-sm text-gray-400">{t('cockpit.no_leak')}</p>
      ) : (
        <div>
          <div className="mb-3 flex items-center gap-3">
            <span className="text-2xl font-bold text-red-600">
              {formatCurrency(leaks.total_leak_amount, 'TRY')}
            </span>
            <Badge variant="danger">
              {t('cockpit.leak_total_opps').replace('{count}', String(leaks.total_leaks))}
            </Badge>
          </div>
          <div className="space-y-2">
            {leaks.items.slice(0, 5).map((item: RevenueLeakItem) => (
              <button
                key={item.opportunity_id}
                type="button"
                onClick={() => navigate(`/opportunities/${item.opportunity_id}`)}
                className="flex w-full items-start justify-between rounded-lg border border-gray-100 dark:border-gray-700 px-4 py-3 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
              >
                <div className="min-w-0 flex-1 text-left">
                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                    {item.title}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {item.owner_name} -{' '}
                    {stageLabels[item.stage as keyof typeof stageLabels] || item.stage}
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {item.factors.map((f) => (
                      <Badge key={f.name} variant="warning" size="sm">
                        {f.label}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="ml-3 flex flex-col items-end gap-1">
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">
                    {formatCurrency(item.amount, 'TRY')}
                  </span>
                  <span
                    className={`text-sm font-bold ${item.leak_score >= 50 ? 'text-red-600' : 'text-amber-600'}`}
                  >
                    {item.leak_score}
                  </span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

// ── Main Page ────────────────────────────────────────

// ── Work Hub Tabs ──────────────────────────────────

type WorkHubTab = 'sequences' | 'feed' | 'todo';

function SequencesTab() {
  const t = useT();
  const { data, isLoading } = useQuery({
    queryKey: ['cockpit', 'sequence-analytics'],
    queryFn: async () => {
      const { sequenceV2Api } = await import('../../lib/api');
      return sequenceV2Api.getAnalytics();
    },
    refetchInterval: 120_000,
  });

  const { data: enrollments } = useQuery({
    queryKey: ['sequences', 'enrollments'],
    queryFn: async () => {
      const { engagementApi } = await import('../../lib/api');
      return engagementApi.listEnrollments();
    },
    refetchInterval: 60_000,
  });

  if (isLoading) return <Skeleton className="h-48 rounded-xl" />;

  const analytics = data || {};
  const activeEnrollments = (enrollments?.enrollments || []).filter(
    (e: Record<string, unknown>) => e.status === 'active',
  );

  return (
    <div className="space-y-4">
      {/* Analytics KPIs */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border p-3">
          <div className="text-xs text-gray-500">{t('cockpit.seq_avg_touch')}</div>
          <div className="text-xl font-semibold">{analytics.avg_touches_per_target ?? '-'}</div>
        </div>
        <div className="rounded-lg border p-3">
          <div className="text-xs text-gray-500">{t('cockpit.seq_total_runs')}</div>
          <div className="text-xl font-semibold">{analytics.total_step_runs ?? 0}</div>
        </div>
        {Object.entries(analytics.status_distribution || {}).map(([status, count]) => (
          <div key={status} className="rounded-lg border p-3">
            <div className="text-xs text-gray-500 capitalize">{status}</div>
            <div className="text-xl font-semibold">{count as number}</div>
          </div>
        ))}
      </div>

      {/* Exit Reason Distribution */}
      {analytics.exit_reason_distribution &&
        Object.keys(analytics.exit_reason_distribution).length > 0 && (
          <Card title={t('cockpit.seq_exit_dist')}>
            <div className="flex flex-wrap gap-2">
              {Object.entries(analytics.exit_reason_distribution).map(([reason, count]) => (
                <Badge key={reason} variant="default">
                  {reason}: {count as number}
                </Badge>
              ))}
            </div>
          </Card>
        )}

      {/* Active Enrollments (next actions) */}
      <Card
        title={t('cockpit.seq_active_title').replace('{count}', String(activeEnrollments.length))}
      >
        {activeEnrollments.length === 0 ? (
          <p className="text-sm text-gray-400">{t('cockpit.seq_no_enrollment')}</p>
        ) : (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {activeEnrollments.slice(0, 15).map((e: Record<string, unknown>) => (
              <div
                key={e.id as number}
                className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm"
              >
                <div>
                  <span className="font-medium">
                    {t('cockpit.seq_enrollment').replace('{id}', String(e.id as number))}
                  </span>
                  <span className="text-gray-500 ml-2">
                    {t('cockpit.seq_step').replace('{step}', String(e.current_step as number))}
                  </span>
                </div>
                <Badge variant={e.is_paused ? 'warning' : 'info'}>
                  {e.is_paused ? t('cockpit.seq_paused') : t('cockpit.seq_active')}
                </Badge>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

export default function CockpitPage() {
  const t = useT();
  const user = useAuthStore((state) => state.user);
  const isManager = user?.role === 'sales_manager';
  const [activeTab, setActiveTab] = useState<WorkHubTab>('feed');

  const workHubTabs = useMemo(
    () =>
      [
        { key: 'sequences' as const, label: t('cockpit.tab_sequences'), icon: Play },
        { key: 'feed' as const, label: t('cockpit.tab_feed'), icon: Activity },
        { key: 'todo' as const, label: t('cockpit.tab_todo'), icon: CheckCircle2 },
      ] as const,
    [t],
  );

  const { data: kpis, isLoading: isKpisLoading } = useQuery<CockpitKpis>({
    queryKey: ['cockpit', 'kpis'],
    queryFn: cockpitApi.getKpis,
    refetchInterval: 60_000,
  });

  return (
    <div className="space-y-6">
      <PageHeader title={t('cockpit.title')} description={t('cockpit.description')} />

      {/* KPI Strip */}
      <KpiStrip data={kpis} isLoading={isKpisLoading} />

      {/* Work Hub — 3 Tab Layout */}
      <div>
        <div className="flex border-b mb-4">
          {workHubTabs.map((tab) => {
            const Icon = tab.icon;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
                  activeTab === tab.key
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                <Icon className="w-4 h-4" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {activeTab === 'sequences' && <SequencesTab />}
        {activeTab === 'feed' && (
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <SignalStream />
            </div>
            <div>
              <TrendCharts />
            </div>
          </div>
        )}
        {activeTab === 'todo' && <ActionQueue />}
      </div>

      {/* Competitive Intel + At-Risk Deals */}
      <div className="grid gap-6 lg:grid-cols-2">
        <CompetitiveIntelPanel />
        <AtRiskDealsPanel />
      </div>

      {/* Revenue Leak Panel (Modul 10) */}
      <RevenueLeakPanel />

      {/* Activity Drought Panel */}
      <ActivityDroughtPanel />

      {/* Playbook Panel */}
      <PlaybookPanel />

      {/* Coaching Panel (manager only) */}
      {isManager && <CoachingPanel />}
    </div>
  );
}
