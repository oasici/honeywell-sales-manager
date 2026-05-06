import { Fragment, useState, useMemo } from 'react';
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
import { EmptyState } from '../../components/ui/EmptyState';
import {
  cockpitApi,
  playbookApi,
  coachingApi,
  aiApi,
  dealHealthApi,
  analyticsApi,
  decisionGapsApi,
  networkBenchmarksApi,
} from '../../lib/api';
import { formatCurrency, formatDate, formatDateTime } from '../../lib/formatters';
import { useAuthStore } from '../../stores/authStore';
import { useT } from '../../hooks/useT';

import type {
  CockpitKpis,
  RevenueSignalItem,
  CockpitAction,
  CockpitRiskyAccount,
  CoachingOverview,
  ActivityDroughtItem,
  RevenueLeakResult,
  RevenueLeakItem,
  CockpitMomentumItem,
  CockpitStallingDealItem,
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

// R6-RENDER-8 — also accept isError so the strip can render a recoverable
// error state instead of a blank page when the cockpit endpoint 500s.
function KpiStrip({
  data,
  isLoading,
  isError,
}: {
  data?: CockpitKpis;
  isLoading: boolean;
  isError?: boolean;
}) {
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
        value: `%${data.win_rate.toFixed(1)}`,
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
        // Surface the severity breakdown — the headline numbers a
        // sales manager actually scans for (audit F-4).
        sub:
          data.signal_stats.critical_count > 0 || data.signal_stats.high_count > 0
            ? `crit ${data.signal_stats.critical_count} · high ${data.signal_stats.high_count}`
            : null,
        subTone: data.signal_stats.critical_count > 0 ? 'danger' : 'warn',
      },
    ];
  }, [data, t]);

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[104px] rounded-2xl" />
        ))}
      </div>
    );
  }

  if (isError) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700 dark:border-red-900/40 dark:bg-red-950/30 dark:text-red-300">
        Cockpit metrikleri yüklenemedi. Sayfayı yenilemeyi deneyin.
      </div>
    );
  }

  if (!data) return null;

  // Linear/Stripe-style KPI tile: 11/600 uppercase eyebrow with icon, then a
  // big tabular-nums value (28/700). The 28px value is what makes the tile
  // feel like a "metric" instead of a tag — the original 20px was too quiet.
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {kpis.map((kpi) => (
        <div
          key={kpi.label}
          className="card-modern flex flex-col gap-2 px-5 py-4 transition-shadow hover:shadow-sm"
        >
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-slate-50 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/50 dark:ring-slate-800">
              {kpi.icon}
            </span>
            <span className="truncate text-overline text-slate-500 dark:text-slate-400">
              {kpi.label}
            </span>
          </div>
          <span className="text-[28px] font-bold leading-none tracking-tight text-slate-900 tabular-nums dark:text-white">
            {kpi.value}
          </span>
          {'sub' in kpi && kpi.sub && (
            <span
              className={[
                'text-[11px] font-medium tabular-nums',
                kpi.subTone === 'danger'
                  ? 'text-red-600 dark:text-red-400'
                  : 'text-amber-600 dark:text-amber-400',
              ].join(' ')}
            >
              {kpi.sub}
            </span>
          )}
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
          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
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
        <EmptyState
          variant="compact"
          icon={<Activity size={22} />}
          title={t('cockpit.signal_empty')}
          description="Şu an aktif bir uyarı yok. Yeni gelişmeler burada listelenecek."
        />
      ) : (
        <div className="max-h-[420px] divide-y divide-slate-100 overflow-y-auto pr-1 dark:divide-slate-800">
          {signals.map((signal) => (
            <div
              key={signal.id}
              className="group flex items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Badge variant={SEVERITY_VARIANT[signal.severity] ?? 'default'} size="sm" dot>
                    {severityLabel[signal.severity as keyof typeof severityLabel] ??
                      signal.severity}
                  </Badge>
                  <span className="text-caption text-slate-400">{signal.signal_type}</span>
                </div>
                {signal.recommended_action && (
                  <p className="mt-1.5 text-body text-slate-700 dark:text-slate-300">
                    {signal.recommended_action}
                  </p>
                )}
                <p className="mt-1 text-caption text-slate-400">
                  {formatDateTime(signal.created_at)}
                </p>
              </div>
              {!signal.is_resolved && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => resolveMutation.mutate(signal.id)}
                  loading={resolveMutation.isPending}
                  title={t('cockpit.resolve_title')}
                  className="opacity-0 transition-opacity group-hover:opacity-100"
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
  const navigate = useNavigate();
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

  const riskLabel = (riskLevel: string | null | undefined): string => {
    switch (riskLevel) {
      case 'healthy':
        return 'Sağlıklı';
      case 'at_risk':
        return 'Risk altında';
      case 'high_risk':
        return 'Yüksek risk';
      case 'critical':
        return 'Kritik';
      default:
        return riskLevel ?? '-';
    }
  };

  const riskVariant = (riskLevel: string | null | undefined): BadgeVariant => {
    switch (riskLevel) {
      case 'critical':
        return 'danger';
      case 'high_risk':
        return 'warning';
      case 'at_risk':
        return 'warning';
      case 'healthy':
        return 'success';
      default:
        return 'default';
    }
  };

  const rottingVariant = (rottingDays: number): BadgeVariant => {
    if (rottingDays >= 30) return 'danger';
    if (rottingDays >= 14) return 'warning';
    return 'default'; // 7-13
  };

  const rottingLabel = (rottingDays: number): string => {
    if (rottingDays >= 30) {
      return t('cockpit.rotting_very_stale').replace('{{n}}', String(rottingDays));
    }
    if (rottingDays >= 14) {
      return t('cockpit.rotting_stale').replace('{{n}}', String(rottingDays));
    }
    return t('cockpit.rotting_compact').replace('{{n}}', String(rottingDays));
  };

  return (
    <Card title={t('cockpit.ai_tasks_card')}>
      {isLoading ? (
        <Skeleton variant="line" count={4} />
      ) : actions.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-400">{t('cockpit.no_pending_tasks')}</p>
      ) : (
        <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1">
          {actions.map((action) => (
            <div
              key={action.id}
              className="rounded-lg border border-slate-100 p-3 dark:border-slate-800"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={PRIORITY_VARIANT[action.priority] ?? 'default'} size="sm">
                    {priorityLabel[action.priority as keyof typeof priorityLabel] ??
                      action.priority}
                  </Badge>
                  {action.deal_health && (
                    <Badge variant={riskVariant(action.deal_health.risk_level)} size="sm">
                      {riskLabel(action.deal_health.risk_level)} • {action.deal_health.score}
                    </Badge>
                  )}
                  {typeof action.open_tasks_count === 'number' && action.open_tasks_count > 0 && (
                    <Badge variant="info" size="sm">
                      {action.open_tasks_count} açık task
                    </Badge>
                  )}
                  {typeof action.rotting_days === 'number' && action.rotting_days >= 7 && (
                    <Badge
                      variant={rottingVariant(action.rotting_days)}
                      size="sm"
                      title={t('board.rotting_tooltip')}
                    >
                      {rottingLabel(action.rotting_days)}
                    </Badge>
                  )}
                </div>
                {action.opportunity_id != null && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => navigate(`/opportunities/${action.opportunity_id}`)}
                  >
                    Fırsatı aç
                  </Button>
                )}
              </div>
              <p className="mt-1 text-sm font-medium text-slate-800 dark:text-slate-200">
                {action.title}
              </p>
              {action.description && (
                <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  {action.description}
                </p>
              )}
              {action.last_activity_at && (
                <p className="mt-1 text-xs text-slate-400">
                  son aktivite: {formatDateTime(action.last_activity_at)}
                </p>
              )}
              {action.due_at && (
                <p className="mt-1 text-xs text-slate-400">
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

// ── Risky accounts (customer health + pipeline load) ─

function RiskyAccountsPanel() {
  const navigate = useNavigate();

  const { data, isLoading } = useQuery<{ items: CockpitRiskyAccount[]; total: number }>({
    queryKey: ['cockpit', 'risky-accounts'],
    queryFn: () => cockpitApi.getRiskyAccounts({ limit: 12 }),
    refetchInterval: 120_000,
  });

  const items = data?.items ?? [];

  const riskLabel = (riskLevel: string | null | undefined): string => {
    switch (riskLevel) {
      case 'healthy':
        return 'Sağlıklı';
      case 'at_risk':
        return 'Risk altında';
      case 'churning':
        return 'Churn riski';
      case 'high_risk':
        return 'Yüksek risk';
      case 'critical':
        return 'Kritik';
      default:
        return riskLevel ?? '-';
    }
  };

  const riskVariant = (riskLevel: string | null | undefined): BadgeVariant => {
    switch (riskLevel) {
      case 'critical':
        return 'danger';
      case 'high_risk':
        return 'danger';
      case 'churning':
        return 'warning';
      case 'at_risk':
        return 'warning';
      case 'healthy':
        return 'success';
      default:
        return 'default';
    }
  };

  return (
    <Card title="Riskli hesaplar">
      {isLoading ? (
        <Skeleton variant="line" count={4} />
      ) : items.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate-400">
          Risk profili yüklenemedi veya uygun hesap bulunamadı.
        </p>
      ) : (
        <div className="max-h-[360px] space-y-3 overflow-y-auto pr-1">
          {items.map((row) => (
            <div
              key={row.customer_id}
              className="flex items-start justify-between gap-3 rounded-lg border border-slate-100 p-3 dark:border-slate-800"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="truncate text-sm font-semibold text-slate-900 dark:text-white">
                    {row.customer_name}
                  </span>
                  <Badge variant={riskVariant(row.health_risk_level)} size="sm">
                    {riskLabel(row.health_risk_level)} • {row.health_score}
                  </Badge>
                </div>
                {row.company && (
                  <p className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
                    {row.company}
                  </p>
                )}
                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-600 dark:text-slate-300">
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 font-semibold dark:bg-slate-800">
                    {row.active_opportunities} açık fırsat
                  </span>
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 font-semibold dark:bg-slate-800">
                    {formatCurrency(row.pipeline_total, 'TRY')} pipeline
                  </span>
                  {row.open_tasks_count > 0 && (
                    <span className="rounded-md bg-violet-100 px-2 py-0.5 font-semibold text-violet-900 dark:bg-violet-900/30 dark:text-violet-200">
                      {row.open_tasks_count} açık task
                    </span>
                  )}
                  {row.unresolved_high_signals > 0 && (
                    <span className="rounded-md bg-amber-100 px-2 py-0.5 font-semibold text-amber-900 dark:bg-amber-900/30 dark:text-amber-200">
                      {row.unresolved_high_signals} yüksek sinyal
                    </span>
                  )}
                </div>
                {row.last_activity_at && (
                  <p className="mt-2 text-xs text-slate-400">
                    son aktivite: {formatDateTime(row.last_activity_at)}
                  </p>
                )}
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => navigate(`/customers/${row.customer_id}`)}
              >
                Hesabı aç
              </Button>
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
        <p className="py-8 text-center text-sm text-slate-400">{t('cockpit.no_trend')}</p>
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
        <p className="py-6 text-center text-sm text-slate-400">{t('cockpit.no_active_playbook')}</p>
      ) : (
        <div className="space-y-2">
          {executions.map((exec) => (
            <div
              key={exec.id}
              className="flex items-center justify-between rounded-lg border border-slate-100 px-4 py-3 dark:border-slate-800"
            >
              <div className="flex items-center gap-3">
                <Play size={16} className="text-green-500" />
                <div>
                  <p className="text-sm font-medium text-slate-800 dark:text-slate-200">
                    {exec.playbook_name}
                  </p>
                  <p className="text-xs text-slate-400">{formatDateTime(exec.started_at)}</p>
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

  // Track which rep rows are expanded so users can drill into the
  // per-indicator score breakdown without leaving the cockpit.
  const [expandedRep, setExpandedRep] = useState<number | null>(null);

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
        <p className="py-6 text-center text-sm text-slate-400">{t('cockpit.data_not_found')}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-slate-200 dark:border-slate-800">
                <th className="pb-2 font-medium text-slate-500 dark:text-slate-400">
                  {t('cockpit.col_rep')}
                </th>
                <th className="pb-2 font-medium text-slate-500 dark:text-slate-400">
                  {t('cockpit.col_score')}
                </th>
                <th className="pb-2 font-medium text-slate-500 dark:text-slate-400">
                  {t('cockpit.col_risk')}
                </th>
                <th className="pb-2 font-medium text-slate-500 dark:text-slate-400">
                  {t('cockpit.col_recommendations')}
                </th>
              </tr>
            </thead>
            <tbody>
              {data.reps.map((rep) => {
                const isExpanded = expandedRep === rep.user_id;
                const hasIndicators = (rep.indicators?.length ?? 0) > 0;
                return (
                  <Fragment key={rep.user_id}>
                    <tr
                      className={`border-b border-slate-100 dark:border-slate-800 ${
                        hasIndicators
                          ? 'cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/40'
                          : ''
                      } ${!isExpanded && 'last:border-0'}`}
                      onClick={() =>
                        hasIndicators && setExpandedRep(isExpanded ? null : rep.user_id)
                      }
                    >
                      <td className="py-2 font-medium text-slate-800 dark:text-slate-200">
                        {hasIndicators && (
                          <span className="mr-1 inline-block w-3 text-slate-400">
                            {isExpanded ? '▾' : '▸'}
                          </span>
                        )}
                        {rep.user_name}
                      </td>
                      <td className="py-2 text-slate-700 dark:text-slate-300">
                        {rep.score.toFixed(0)}
                      </td>
                      <td className="py-2">
                        <Badge variant={riskVariant(rep.risk_level)} size="sm">
                          {rep.risk_level}
                        </Badge>
                      </td>
                      <td className="py-2 text-xs text-slate-500 dark:text-slate-400">
                        {rep.recommendations.slice(0, 2).join('; ')}
                      </td>
                    </tr>
                    {isExpanded && hasIndicators && (
                      <tr className="border-b border-slate-100 last:border-0 dark:border-slate-800 bg-slate-50/40 dark:bg-slate-900/40">
                        <td colSpan={4} className="py-2 px-3">
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                            {rep.indicators.map((ind) => (
                              <div
                                key={ind.name}
                                className="rounded border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-2 py-1.5"
                              >
                                <p className="text-[10px] uppercase tracking-wide text-slate-500">
                                  {ind.label}
                                </p>
                                <p className="text-sm font-semibold text-slate-900 dark:text-white">
                                  {ind.score.toFixed(0)}
                                  <span className="ml-1 text-[10px] text-slate-400">
                                    × {ind.weight.toFixed(2)}
                                  </span>
                                </p>
                              </div>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
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
        <p className="py-6 text-center text-sm text-slate-400">{t('cockpit.no_comp_mentions')}</p>
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
                    className="rounded-lg border border-slate-100 dark:border-slate-800 px-4 py-3"
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2">
                        <Swords size={14} className="text-red-400" />
                        <span className="text-sm font-semibold text-slate-900 dark:text-white">
                          {compName}
                        </span>
                      </div>
                      <Badge variant={comp.mention_count > 5 ? 'danger' : 'info'} size="sm">
                        {t('cockpit.mentions_count').replace('{count}', String(comp.mention_count))}
                      </Badge>
                    </div>
                    {comp.sentiment_avg != null && (
                      <p className="text-xs text-slate-500 mb-1">
                        {t('cockpit.sentiment')}{' '}
                        {comp.sentiment_avg > 0
                          ? t('cockpit.sentiment_positive')
                          : comp.sentiment_avg < 0
                            ? t('cockpit.sentiment_negative')
                            : t('cockpit.sentiment_neutral')}
                      </p>
                    )}
                    {comp.recent_mentions?.slice(0, 3).map((m, i) => (
                      <p key={i} className="text-xs text-slate-400 truncate">
                        [{m.source_type}] {m.context_snippet}
                      </p>
                    ))}
                    {(comp.recent_mentions?.length ?? 0) > 3 && (
                      <p className="mt-0.5 text-[11px] text-slate-500">
                        +{(comp.recent_mentions?.length ?? 0) - 3} {t('cockpit.more_mentions')}
                      </p>
                    )}
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
        <p className="py-6 text-center text-sm text-slate-400">{t('cockpit.no_at_risk')}</p>
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
                  className="flex w-full items-center justify-between rounded-lg border border-slate-100 dark:border-slate-800 px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <ShieldAlert
                      size={14}
                      className={deal.score < 30 ? 'text-red-500' : 'text-amber-500'}
                    />
                    <span className="text-sm font-medium text-slate-900 dark:text-white truncate">
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
        <p className="py-6 text-center text-sm text-slate-400">{t('cockpit.no_drought')}</p>
      ) : (
        <div className="space-y-2">
          {items.slice(0, 7).map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => navigate(`/opportunities/${item.id}`)}
              className="flex w-full items-center justify-between rounded-lg border border-slate-100 dark:border-slate-800 px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              <div className="flex items-center gap-2 min-w-0">
                <Clock
                  size={14}
                  className={item.days_since_last > 14 ? 'text-red-500' : 'text-amber-500'}
                />
                <div className="min-w-0 text-left">
                  <span className="text-sm font-medium text-slate-900 dark:text-white truncate block">
                    {item.title}
                  </span>
                  <span className="text-xs text-slate-400">
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
        <p className="py-6 text-center text-sm text-slate-400">{t('cockpit.no_leak')}</p>
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
                className="flex w-full items-start justify-between rounded-lg border border-slate-100 dark:border-slate-800 px-4 py-3 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
              >
                <div className="min-w-0 flex-1 text-left">
                  <p className="text-sm font-medium text-slate-900 dark:text-white truncate">
                    {item.title}
                  </p>
                  <p className="text-xs text-slate-400 mt-0.5">
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
                  <span className="text-sm font-semibold text-slate-900 dark:text-white">
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
  const isManager = useAuthStore((s) => s.user?.role === 'sales_manager');

  const { data, isLoading } = useQuery({
    queryKey: ['cockpit', 'sequence-analytics'],
    queryFn: async () => {
      const { sequenceV2Api } = await import('../../lib/api');
      return sequenceV2Api.getAnalytics();
    },
    enabled: Boolean(isManager),
    refetchInterval: 120_000,
  });

  const { data: perfData, isLoading: perfLoading } = useQuery({
    queryKey: ['cockpit', 'sequence-performance'],
    queryFn: async () => {
      const { sequenceV2Api } = await import('../../lib/api');
      return sequenceV2Api.getPerformance();
    },
    enabled: Boolean(isManager),
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

  if (isManager && (isLoading || perfLoading)) return <Skeleton className="h-48 rounded-xl" />;

  const analytics = data || {};
  const perfSequences = (perfData?.sequences || []) as Array<Record<string, unknown>>;
  const activeEnrollments = (enrollments?.enrollments || []).filter(
    (e: Record<string, unknown>) => e.status === 'active',
  );

  if (!isManager) {
    return (
      <div className="space-y-4">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          {t('cockpit.seq_manager_only')}
        </p>
        <Card
          title={t('cockpit.seq_active_title').replace('{count}', String(activeEnrollments.length))}
        >
          {activeEnrollments.length === 0 ? (
            <p className="text-sm text-slate-400">{t('cockpit.seq_no_enrollment')}</p>
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
                    <span className="text-slate-500 ml-2">
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

  return (
    <div className="space-y-4">
      {/* Analytics KPIs */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border p-3">
          <div className="text-xs text-slate-500">{t('cockpit.seq_avg_touch')}</div>
          <div className="text-xl font-semibold">{analytics.avg_touches_per_target ?? '-'}</div>
        </div>
        <div className="rounded-lg border p-3">
          <div className="text-xs text-slate-500">{t('cockpit.seq_total_runs')}</div>
          <div className="text-xl font-semibold">{analytics.total_step_runs ?? 0}</div>
        </div>
        {Object.entries(analytics.status_distribution || {}).map(([status, count]) => (
          <div key={status} className="rounded-lg border p-3">
            <div className="text-xs text-slate-500 capitalize">{status}</div>
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

      <Card title={t('cockpit.seq_perf_title')}>
        {perfSequences.length === 0 ? (
          <p className="text-sm text-slate-400">{t('cockpit.seq_perf_empty')}</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead>
                <tr className="border-b text-xs text-slate-500">
                  <th className="py-2 pr-3 font-medium">{t('cockpit.seq_perf_col_name')}</th>
                  <th className="py-2 pr-3 font-medium text-right">
                    {t('cockpit.seq_perf_col_total')}
                  </th>
                  <th className="py-2 pr-3 font-medium text-right">
                    {t('cockpit.seq_perf_col_active')}
                  </th>
                  <th className="py-2 pr-3 font-medium text-right">
                    {t('cockpit.seq_perf_col_done')}
                  </th>
                  <th className="py-2 pr-3 font-medium text-right">
                    {t('cockpit.seq_perf_col_exit')}
                  </th>
                  <th className="py-2 font-medium text-right">{t('cockpit.seq_perf_col_avg')}</th>
                </tr>
              </thead>
              <tbody>
                {perfSequences.map((row) => (
                  <tr
                    key={String(row.sequence_id)}
                    className="border-b border-slate-100 dark:border-slate-800"
                  >
                    <td className="py-2 pr-3 font-medium text-slate-900 dark:text-white">
                      {String(row.name)}
                      {!row.is_active ? (
                        <span className="ml-2 text-xs font-normal text-slate-400">
                          ({t('opp_detail.inactive')})
                        </span>
                      ) : null}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {Number(row.enrollments_total ?? 0)}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {Number(row.enrollments_active ?? 0)}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {Number(row.enrollments_completed ?? 0)}
                    </td>
                    <td className="py-2 pr-3 text-right tabular-nums">
                      {Number(row.enrollments_exited ?? 0)}
                    </td>
                    <td className="py-2 text-right tabular-nums">
                      {Number(row.avg_completed_steps_per_enrollment ?? 0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* Active Enrollments (next actions) */}
      <Card
        title={t('cockpit.seq_active_title').replace('{count}', String(activeEnrollments.length))}
      >
        {activeEnrollments.length === 0 ? (
          <p className="text-sm text-slate-400">{t('cockpit.seq_no_enrollment')}</p>
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
                  <span className="text-slate-500 ml-2">
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

function MomentumDeclinePanel() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery<{
    snapshot_date: string | null;
    items: CockpitMomentumItem[];
    total: number;
  }>({
    queryKey: ['cockpit', 'momentum'],
    queryFn: () => cockpitApi.getMomentum({ limit: 10 }),
    refetchInterval: 120_000,
  });

  const items = data?.items ?? [];

  const bandVariant = (band: string | null | undefined): BadgeVariant => {
    switch (band) {
      case 'dead':
        return 'danger';
      case 'declining':
        return 'warning';
      case 'steady':
        return 'default';
      case 'accelerating':
        return 'success';
      default:
        return 'default';
    }
  };

  return (
    <Card title="Momentum düşen fırsatlar">
      {isLoading ? (
        <Skeleton variant="line" count={4} />
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-400">Düşen momentum yok</p>
      ) : (
        <div className="space-y-3">
          {items.map((o) => (
            <div
              key={o.id}
              className="flex items-start justify-between gap-3 rounded-lg border border-slate-100 p-3 dark:border-slate-800"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={bandVariant(o.momentum_band)} size="sm">
                    {o.momentum_band ?? 'unknown'} • {o.momentum_score ?? '-'}
                  </Badge>
                  <span className="text-xs text-slate-400">{o.stage}</span>
                </div>
                <p className="mt-1 truncate text-sm font-medium text-slate-800 dark:text-slate-200">
                  {o.title}
                </p>
                {o.drivers?.[0]?.label && (
                  <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
                    {o.drivers[0].label}
                  </p>
                )}
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => navigate(`/opportunities/${o.id}`)}
              >
                Aç
              </Button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function StallingDealsPanel() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery<{
    snapshot_date: string | null;
    items: CockpitStallingDealItem[];
    total: number;
  }>({
    queryKey: ['cockpit', 'buyer-state', 'stalling'],
    queryFn: () => cockpitApi.getStallingDeals({ limit: 10 }),
    refetchInterval: 120_000,
  });

  const items = data?.items ?? [];

  return (
    <Card title="Stalling deals (Buyer State)">
      {isLoading ? (
        <Skeleton variant="line" count={4} />
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-400">Stalling deal yok</p>
      ) : (
        <div className="space-y-3">
          {items.map((o) => (
            <div
              key={o.id}
              className="flex items-start justify-between gap-3 rounded-lg border border-slate-100 p-3 dark:border-slate-800"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant="warning" size="sm">
                    stalling
                  </Badge>
                  {typeof o.days_since_last_buyer_touch === 'number' && (
                    <Badge variant="default" size="sm">
                      buyer sessizliği: {o.days_since_last_buyer_touch}g
                    </Badge>
                  )}
                  {o.negative_signal_count_14d > 0 && (
                    <Badge variant="danger" size="sm">
                      neg: {o.negative_signal_count_14d}
                    </Badge>
                  )}
                </div>
                <p className="mt-1 truncate text-sm font-medium text-slate-800 dark:text-slate-200">
                  {o.title}
                </p>
                <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                  stage: {o.stage} • meetings(30g): {o.meeting_count_30d} • replies(14g):{' '}
                  {o.buyer_reply_count_14d}
                </p>
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => navigate(`/opportunities/${o.id}`)}
              >
                Aç
              </Button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function DecisionGapsPanel() {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ['cockpit', 'decision-gaps'],
    queryFn: () => decisionGapsApi.cockpitList({ limit: 10 }),
    refetchInterval: 120_000,
  });

  const items = data?.items ?? [];
  return (
    <Card title="Decision Gaps (Öncelikli Eksikler)">
      {isLoading ? (
        <Skeleton variant="line" count={4} />
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-400">Gap yok</p>
      ) : (
        <div className="space-y-3">
          {items.map((g: any) => (
            <div
              key={g.id}
              className="flex items-start justify-between gap-3 rounded-lg border border-slate-100 p-3 dark:border-slate-800"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <Badge variant={SEVERITY_VARIANT[g.severity] ?? 'default'} size="sm">
                    {g.severity}
                  </Badge>
                  <span className="text-xs text-slate-400">{g.gap_type}</span>
                </div>
                <p className="mt-1 truncate text-sm font-medium text-slate-800 dark:text-slate-200">
                  {g.title}
                </p>
                {/* Show every recommended action as a chip rather than
                    truncating to the first one — the API used to drop
                    the rest, so reps couldn't see the full guidance.
                    Falls back to the legacy headline string if the
                    plural field is empty (older payloads). */}
                {/* The wrapping ``items.map`` types ``g`` as ``any``,
                    which leaks into the chip array's map callback and
                    produces TS7006 under strict noImplicitAny. We
                    pin the action array to ``string[]`` here so the
                    inner callback gets the correct types. */}
                {((g.recommended_actions ?? []) as string[]).length > 0 ? (
                  <ul className="mt-1 flex flex-wrap gap-1">
                    {((g.recommended_actions ?? []) as string[])
                      .slice(0, 4)
                      .map((action: string, i: number) => (
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
                ) : (
                  g.recommended_action && (
                    <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400 line-clamp-2">
                      {g.recommended_action}
                    </p>
                  )
                )}
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => navigate(`/opportunities/${g.opportunity_id}`)}
              >
                Aç
              </Button>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function SegmentBenchmarksPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['benchmarks', 'segments', 'latest'],
    queryFn: () => networkBenchmarksApi.getLatestSegments(8),
    refetchInterval: 300_000,
  });

  const items = data?.items ?? [];
  return (
    <Card title="Segment Benchmarks (Günlük)">
      {isLoading ? (
        <Skeleton variant="line" count={4} />
      ) : items.length === 0 ? (
        <p className="py-8 text-center text-sm text-slate-400">Benchmark yok</p>
      ) : (
        <div className="space-y-3">
          {items.map((s: any) => (
            <div
              key={s.segment_key}
              className="rounded-lg border border-slate-100 p-3 dark:border-slate-800"
            >
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-slate-900 dark:text-white">
                  {s.segment_key}
                </p>
                <Badge variant="default" size="sm">
                  n={s.sample_size}
                </Badge>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-600 dark:text-slate-300">
                <div>followup median: {s.followup_median_days ?? '-'}</div>
                <div>avg discount: {s.avg_discount_pct ?? '-'}</div>
                <div>avg stakeholders: {s.avg_stakeholder_count ?? '-'}</div>
                <div>objection rate: {s.objection_rate_14d ?? '-'}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
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

  const { data: kpis, isLoading: isKpisLoading, isError: isKpisError } = useQuery<CockpitKpis>({
    queryKey: ['cockpit', 'kpis'],
    queryFn: cockpitApi.getKpis,
    refetchInterval: 60_000,
  });

  return (
    <div className="space-y-6">
      <PageHeader title={t('cockpit.title')} description={t('cockpit.description')} />

      {/* KPI Strip */}
      <KpiStrip data={kpis} isLoading={isKpisLoading} isError={isKpisError} />

      <RiskyAccountsPanel />
      <MomentumDeclinePanel />
      <StallingDealsPanel />
      <DecisionGapsPanel />
      {isManager && <SegmentBenchmarksPanel />}

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
                    : 'border-transparent text-slate-500 hover:text-slate-700'
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
