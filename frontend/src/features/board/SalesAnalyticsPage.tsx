import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { analyticsApi, opsApi, forecastApi } from '../../lib/api';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { Badge } from '../../components/ui/Badge';
import { formatCurrency } from '../../lib/formatters';
import { useAuthStore } from '../../stores/authStore';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts';

import type {
  TeamRollupRow,
  ForecastAccuracy,
  RevenueWaterfallResult,
  RevenueLeakResult,
  RevenueLeakItem,
} from '../../lib/types';

const ACCURACY_RING_RADIUS = 36;
const ACCURACY_RING_CIRCUMFERENCE = 2 * Math.PI * ACCURACY_RING_RADIUS;

function AccuracyRing({ score }: { score: number }) {
  const color = score >= 70 ? '#22c55e' : score >= 40 ? '#f59e0b' : '#ef4444';
  const pct = Math.min(score, 100);
  const offset = ACCURACY_RING_CIRCUMFERENCE - (pct / 100) * ACCURACY_RING_CIRCUMFERENCE;

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
          strokeDasharray={ACCURACY_RING_CIRCUMFERENCE}
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

const FUNNEL_COLORS = ['#3b82f6', '#6366f1', '#8b5cf6', '#a855f7', '#22c55e', '#ef4444', '#94a3b8'];
const STAGE_LABELS: Record<string, string> = {
  draft: 'Taslak',
  pending_approval: 'Onay Bekliyor',
  approved: 'Onaylandi',
  sent: 'Gonderildi',
  accepted: 'Kabul',
  rejected: 'Reddedildi',
  expired: 'Suresi Doldu',
};

interface WoWWeek {
  week_label: string;
  total: number;
}

interface WoWData {
  weeks: WoWWeek[];
  current_total: number;
  previous_total: number;
  delta: number;
  delta_pct: number;
}

interface TeamRollupResponse {
  reps: TeamRollupRow[];
  grand_total: {
    commit: number;
    best_case: number;
    pipeline: number;
    total: number;
    opportunity_count: number;
  };
}

export default function SalesAnalyticsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isManager = user?.role === 'manager' || user?.role === 'admin';

  const { data: forecast, isLoading: fLoading } = useQuery({
    queryKey: ['forecast'],
    queryFn: () => analyticsApi.getForecast(30),
  });

  const { data: teamRollup } = useQuery<TeamRollupResponse>({
    queryKey: ['forecast', 'team-rollup'],
    queryFn: () => forecastApi.getTeamRollup(),
    enabled: isManager,
  });

  const { data: wow } = useQuery<WoWData>({
    queryKey: ['forecast-wow'],
    queryFn: () => forecastApi.getWoW(4),
  });

  const snapshotMutation = useMutation({
    mutationFn: () => forecastApi.takeSnapshot(),
    onSuccess: () => {
      toast.success('Pipeline snapshot alindi');
      queryClient.invalidateQueries({ queryKey: ['forecast-wow'] });
    },
  });
  const { data: funnel } = useQuery({
    queryKey: ['funnel'],
    queryFn: () => analyticsApi.getFunnel(90),
  });
  const { data: scorecards } = useQuery({
    queryKey: ['scorecards'],
    queryFn: () => analyticsApi.getRepScorecards(30),
  });
  const { data: sla } = useQuery({
    queryKey: ['sla'],
    queryFn: () => analyticsApi.getSla(30),
  });
  const { data: discounts } = useQuery({
    queryKey: ['discounts'],
    queryFn: () => analyticsApi.getDiscounts(90),
  });
  const { data: winLoss } = useQuery({
    queryKey: ['winLoss'],
    queryFn: () => analyticsApi.getWinLossReasons(90),
  });
  const { data: dataQuality } = useQuery({
    queryKey: ['dataQuality'],
    queryFn: analyticsApi.getDataQuality,
  });
  const { data: forecastAccuracy } = useQuery<ForecastAccuracy>({
    queryKey: ['forecast-accuracy'],
    queryFn: () => forecastApi.getAccuracy(),
    enabled: isManager,
  });
  const { data: queues } = useQuery({
    queryKey: ['queues'],
    queryFn: opsApi.getQueues,
  });

  // Waterfall period selector
  const [waterfallPeriod, setWaterfallPeriod] = useState<string>('this_month');

  const getWaterfallDates = (): { from: string; to: string } => {
    const now = new Date();
    if (waterfallPeriod === 'last_month') {
      const from = new Date(now.getFullYear(), now.getMonth() - 1, 1);
      const to = new Date(now.getFullYear(), now.getMonth(), 0, 23, 59, 59);
      return { from: from.toISOString(), to: to.toISOString() };
    }
    if (waterfallPeriod === 'this_quarter') {
      const quarterMonth = Math.floor(now.getMonth() / 3) * 3;
      const from = new Date(now.getFullYear(), quarterMonth, 1);
      return { from: from.toISOString(), to: now.toISOString() };
    }
    // this_month
    const from = new Date(now.getFullYear(), now.getMonth(), 1);
    return { from: from.toISOString(), to: now.toISOString() };
  };

  const waterfallDates = getWaterfallDates();

  const { data: waterfallRaw } = useQuery({
    queryKey: ['waterfall', waterfallPeriod],
    queryFn: () => analyticsApi.getWaterfall(waterfallDates.from, waterfallDates.to),
  });
  const waterfall: RevenueWaterfallResult | undefined = waterfallRaw?.data;

  const { data: leaksRaw } = useQuery({
    queryKey: ['revenue-leaks'],
    queryFn: () => analyticsApi.getRevenueLeaks(),
  });
  const leaks: RevenueLeakResult | undefined = leaksRaw?.data;

  if (fLoading) return <Skeleton variant="card" count={4} />;

  return (
    <div>
      <PageHeader
        title="Satis Analitiği"
        description="Pipeline, performans ve operasyonel metrikler"
      />

      {/* Row 1: Forecast + Pipeline KPIs */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5 mb-6">
        <Card>
          <div className="p-4">
            <p className="text-xs font-medium text-gray-600 dark:text-gray-300">Acik Pipeline</p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              {formatCurrency(forecast?.open_quotes_total || 0, 'TRY')}
            </p>
          </div>
        </Card>
        <Card>
          <div className="p-4">
            <p className="text-xs font-medium text-gray-600 dark:text-gray-300">
              Forecast (30 gun)
            </p>
            <p className="text-2xl font-bold text-green-600">
              {formatCurrency(forecast?.forecast_total || 0, 'TRY')}
            </p>
            <p className="text-[10px] text-gray-400">
              Kazanma orani: %{((forecast?.win_rate || 0) * 100).toFixed(0)}
            </p>
          </div>
        </Card>
        <Card>
          <div className="p-4">
            <p className="text-xs font-medium text-gray-600 dark:text-gray-300">SLA Medyan Yanit</p>
            <p
              className={`text-2xl font-bold ${(sla?.median_first_action_minutes || 0) > 480 ? 'text-red-600' : 'text-gray-900 dark:text-white'}`}
            >
              {sla?.median_first_action_minutes || 0} dk
            </p>
            <p className="text-[10px] text-gray-400">{sla?.breaches_count || 0} ihlal</p>
          </div>
        </Card>
        <Card>
          <div className="p-4">
            <p className="text-xs font-medium text-gray-600 dark:text-gray-300">
              Indirim p50 / p90
            </p>
            <p className="text-2xl font-bold text-gray-900 dark:text-white">
              %{discounts?.p50_discount_rate || 0} / %{discounts?.p90_discount_rate || 0}
            </p>
          </div>
        </Card>

        {/* WoW Pipeline Change */}
        <Card>
          <div className="p-4">
            <p className="text-xs font-medium text-gray-600 dark:text-gray-300">
              Haftalik Pipeline Degisimi
            </p>
            {wow ? (
              <>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {formatCurrency(wow.current_total, 'TRY')}
                </p>
                <div className="mt-1 flex items-center gap-1">
                  <span
                    className={`text-xs font-semibold ${wow.delta >= 0 ? 'text-green-600' : 'text-red-600'}`}
                  >
                    {wow.delta >= 0 ? '\u2191' : '\u2193'}{' '}
                    {formatCurrency(Math.abs(wow.delta), 'TRY')}
                  </span>
                  <span
                    className={`text-[10px] ${wow.delta >= 0 ? 'text-green-500' : 'text-red-500'}`}
                  >
                    ({wow.delta_pct >= 0 ? '+' : ''}
                    {wow.delta_pct?.toFixed(1)}%)
                  </span>
                </div>
                {isManager && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="mt-2 w-full text-xs"
                    loading={snapshotMutation.isPending}
                    onClick={() => snapshotMutation.mutate()}
                  >
                    Snapshot Al
                  </Button>
                )}
              </>
            ) : (
              <Skeleton variant="card" />
            )}
          </div>
        </Card>
      </div>

      {/* WoW Bar Chart */}
      {wow?.weeks && wow.weeks.length > 0 && (
        <Card title="Haftalik Pipeline Trend (Son 4 Hafta)" className="mb-6">
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={wow.weeks}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="week_label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip formatter={(value) => formatCurrency(Number(value), 'TRY')} />
                <Bar dataKey="total" fill="#6366f1" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* Team Forecast Rollup (managers only) */}
      {isManager && teamRollup?.reps && teamRollup.reps.length > 0 && (
        <Card title="Takim Tahmin Rollup" className="mb-6">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="py-3 px-4 text-left text-xs font-semibold text-gray-500 uppercase">
                    Temsilci
                  </th>
                  <th className="py-3 px-4 text-right text-xs font-semibold text-gray-500 uppercase">
                    Kesin
                  </th>
                  <th className="py-3 px-4 text-right text-xs font-semibold text-gray-500 uppercase">
                    En Iyi Durum
                  </th>
                  <th className="py-3 px-4 text-right text-xs font-semibold text-gray-500 uppercase">
                    Pipeline
                  </th>
                  <th className="py-3 px-4 text-right text-xs font-semibold text-gray-500 uppercase">
                    Toplam
                  </th>
                </tr>
              </thead>
              <tbody>
                {teamRollup.reps.map((row) => (
                  <tr
                    key={row.user_id}
                    className="cursor-pointer border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50"
                    onClick={() => navigate(`/coaching/rep/${row.user_id}`)}
                  >
                    <td className="py-2.5 px-4 font-medium text-gray-900 dark:text-white">
                      {row.user_name}
                    </td>
                    <td className="py-2.5 px-4 text-right">{formatCurrency(row.commit, 'TRY')}</td>
                    <td className="py-2.5 px-4 text-right">
                      {formatCurrency(row.best_case, 'TRY')}
                    </td>
                    <td className="py-2.5 px-4 text-right">
                      {formatCurrency(row.pipeline, 'TRY')}
                    </td>
                    <td className="py-2.5 px-4 text-right font-semibold">
                      {formatCurrency(row.total, 'TRY')}
                    </td>
                  </tr>
                ))}
              </tbody>
              {teamRollup.grand_total && (
                <tfoot>
                  <tr className="border-t-2 border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800/50">
                    <td className="py-2.5 px-4 font-bold text-gray-900 dark:text-white">
                      Genel Toplam
                    </td>
                    <td className="py-2.5 px-4 text-right font-bold">
                      {formatCurrency(teamRollup.grand_total.commit, 'TRY')}
                    </td>
                    <td className="py-2.5 px-4 text-right font-bold">
                      {formatCurrency(teamRollup.grand_total.best_case, 'TRY')}
                    </td>
                    <td className="py-2.5 px-4 text-right font-bold">
                      {formatCurrency(teamRollup.grand_total.pipeline, 'TRY')}
                    </td>
                    <td className="py-2.5 px-4 text-right font-bold">
                      {formatCurrency(teamRollup.grand_total.total, 'TRY')}
                    </td>
                  </tr>
                </tfoot>
              )}
            </table>
          </div>
        </Card>
      )}

      {/* Forecast Accuracy (Modul 12) */}
      {isManager && forecastAccuracy && (
        <Card title="Tahmin Dogrulugu" className="mb-6">
          <div className="flex items-start gap-6">
            <AccuracyRing score={Math.round(forecastAccuracy.accuracy_pct)} />
            <div className="flex-1 space-y-3">
              <div className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <span className="text-xs text-gray-500 dark:text-gray-400">Donem</span>
                  <p className="font-semibold text-gray-900 dark:text-white">
                    {forecastAccuracy.period}
                  </p>
                </div>
                <div>
                  <span className="text-xs text-gray-500 dark:text-gray-400">Tahmin</span>
                  <p className="font-semibold text-gray-900 dark:text-white">
                    {formatCurrency(forecastAccuracy.commit_forecast, 'TRY')}
                  </p>
                </div>
                <div>
                  <span className="text-xs text-gray-500 dark:text-gray-400">Gerceklesen</span>
                  <p className="font-semibold text-gray-900 dark:text-white">
                    {formatCurrency(forecastAccuracy.actual_won, 'TRY')}
                  </p>
                </div>
              </div>
              {forecastAccuracy.per_rep.length > 0 && (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 dark:border-gray-700">
                        <th className="py-2 px-3 text-left text-xs text-gray-500">Temsilci</th>
                        <th className="py-2 px-3 text-right text-xs text-gray-500">Tahmin</th>
                        <th className="py-2 px-3 text-right text-xs text-gray-500">Gerceklesen</th>
                        <th className="py-2 px-3 text-right text-xs text-gray-500">Dogruluk %</th>
                      </tr>
                    </thead>
                    <tbody>
                      {forecastAccuracy.per_rep.map((rep) => (
                        <tr
                          key={rep.user_id}
                          className="border-b border-gray-50 dark:border-gray-800"
                        >
                          <td className="py-2 px-3 font-medium text-gray-900 dark:text-white">
                            {rep.user_name}
                          </td>
                          <td className="py-2 px-3 text-right">
                            {formatCurrency(rep.forecast, 'TRY')}
                          </td>
                          <td className="py-2 px-3 text-right">
                            {formatCurrency(rep.actual, 'TRY')}
                          </td>
                          <td className="py-2 px-3 text-right">
                            <span
                              className={`font-bold ${rep.accuracy >= 70 ? 'text-green-600' : rep.accuracy >= 40 ? 'text-amber-600' : 'text-red-600'}`}
                            >
                              %{rep.accuracy}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* Row 2: Funnel + Win/Loss */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 mb-6">
        <Card title="Teklif Donusum Hunisi">
          {funnel?.funnel ? (
            <div className="space-y-2 p-2">
              {funnel.funnel.map((s: { stage: string; count: number; pct: number }, i: number) => (
                <div key={s.stage} className="flex items-center gap-3">
                  <span className="w-24 text-xs text-gray-600 dark:text-gray-400 truncate">
                    {STAGE_LABELS[s.stage] || s.stage}
                  </span>
                  <div className="flex-1 h-6 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${Math.max(s.pct, 2)}%`,
                        backgroundColor: FUNNEL_COLORS[i % FUNNEL_COLORS.length],
                      }}
                    />
                  </div>
                  <span className="w-16 text-right text-xs font-semibold text-gray-700 dark:text-gray-300">
                    {s.count} (%{s.pct})
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-gray-400">Veri yok</p>
          )}
        </Card>

        <Card title="Kazanma/Kaybetme Nedenleri">
          {winLoss?.reasons && winLoss.reasons.length > 0 ? (
            <div className="h-[250px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={winLoss.reasons} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis dataKey="reason" type="category" tick={{ fontSize: 10 }} width={100} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#6366f1" radius={[0, 6, 6, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-gray-400">
              Henuz kapanis nedeni girilmemis
            </p>
          )}
        </Card>
      </div>

      {/* Row 3: Rep Scorecards */}
      <Card title="Temsilci Performansi" className="mb-6">
        {scorecards?.scorecards && scorecards.scorecards.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="py-3 px-4 text-left text-xs font-semibold text-gray-500 uppercase">
                    Temsilci
                  </th>
                  <th className="py-3 px-4 text-center text-xs font-semibold text-gray-500 uppercase">
                    Teklif
                  </th>
                  <th className="py-3 px-4 text-center text-xs font-semibold text-gray-500 uppercase">
                    Gonderilen
                  </th>
                  <th className="py-3 px-4 text-center text-xs font-semibold text-gray-500 uppercase">
                    Kazanilan
                  </th>
                  <th className="py-3 px-4 text-center text-xs font-semibold text-gray-500 uppercase">
                    Kazanma %
                  </th>
                  <th className="py-3 px-4 text-right text-xs font-semibold text-gray-500 uppercase">
                    Gelir
                  </th>
                  <th className="py-3 px-4 text-right text-xs font-semibold text-gray-500 uppercase">
                    Ort. Indirim
                  </th>
                </tr>
              </thead>
              <tbody>
                {scorecards.scorecards.map((r: Record<string, unknown>) => (
                  <tr
                    key={r.user_id as number}
                    className="border-b border-gray-50 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-800/50"
                  >
                    <td className="py-2.5 px-4 font-medium text-gray-900 dark:text-white">
                      {r.full_name as string}
                    </td>
                    <td className="py-2.5 px-4 text-center">{r.quote_count as number}</td>
                    <td className="py-2.5 px-4 text-center">{r.sent_count as number}</td>
                    <td className="py-2.5 px-4 text-center">{r.won_count as number}</td>
                    <td className="py-2.5 px-4 text-center">
                      <span
                        className={`font-semibold ${(r.win_rate as number) >= 50 ? 'text-green-600' : (r.win_rate as number) >= 30 ? 'text-yellow-600' : 'text-red-600'}`}
                      >
                        %{r.win_rate as number}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-right font-medium">
                      {formatCurrency(r.revenue as number, 'TRY')}
                    </td>
                    <td className="py-2.5 px-4 text-right">
                      {formatCurrency(r.avg_discount as number, 'TRY')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="py-8 text-center text-sm text-gray-400">Veri yok</p>
        )}
      </Card>

      {/* Row 4: Data Quality + Ops Queues */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 mb-6">
        <Card title="Veri Kalitesi">
          {dataQuality ? (
            <div className="space-y-4 p-2">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Musteriler
                  </span>
                  <span className="text-sm font-bold text-gray-900 dark:text-white">
                    %{dataQuality.customers?.completeness_pct || 0}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-gray-100 dark:bg-gray-800">
                  <div
                    className="h-2 rounded-full bg-green-500 transition-all"
                    style={{ width: `${dataQuality.customers?.completeness_pct || 0}%` }}
                  />
                </div>
                <p className="mt-1 text-[10px] text-gray-400">
                  Eksik telefon: {dataQuality.customers?.missing_phone || 0} | Eksik firma:{' '}
                  {dataQuality.customers?.missing_company || 0}
                </p>
              </div>
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Teklifler
                  </span>
                  <span className="text-sm font-bold text-gray-900 dark:text-white">
                    %{dataQuality.quotes?.completeness_pct || 0}
                  </span>
                </div>
                <div className="h-2 rounded-full bg-gray-100 dark:bg-gray-800">
                  <div
                    className="h-2 rounded-full bg-blue-500 transition-all"
                    style={{ width: `${dataQuality.quotes?.completeness_pct || 0}%` }}
                  />
                </div>
                <p className="mt-1 text-[10px] text-gray-400">
                  Musterisiz: {dataQuality.quotes?.missing_customer || 0} | Kalemsiz:{' '}
                  {dataQuality.quotes?.missing_items || 0}
                </p>
              </div>
            </div>
          ) : (
            <Skeleton variant="card" />
          )}
        </Card>

        <Card title="Operasyonel Kuyruklar">
          {queues ? (
            <div className="space-y-3 p-2">
              <div className="flex items-center justify-between rounded-lg border border-yellow-200 bg-yellow-50 px-4 py-3 dark:border-yellow-800 dark:bg-yellow-900/20">
                <span className="text-sm text-yellow-800 dark:text-yellow-200">
                  Inceleme Bekleyen Email
                </span>
                <Badge variant="warning">{queues.review_pending_count || 0}</Badge>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 dark:border-blue-800 dark:bg-blue-900/20">
                <span className="text-sm text-blue-800 dark:text-blue-200">
                  Onay Bekleyen Teklif
                </span>
                <Badge variant="info">{queues.approval_pending_count || 0}</Badge>
              </div>
              <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-4 py-3 dark:border-red-800 dark:bg-red-900/20">
                <span className="text-sm text-red-800 dark:text-red-200">
                  Suresi Dolacak Teklifler
                </span>
                <Badge variant="danger">{queues.expiring_count || 0}</Badge>
              </div>
            </div>
          ) : (
            <Skeleton variant="card" />
          )}
        </Card>
      </div>

      {/* Row 5: Discount Outliers + SLA Breaches */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {discounts?.outliers && discounts.outliers.length > 0 && (
          <Card title={`Yuksek Indirimli Teklifler (>${discounts.threshold_pct || 25}%)`}>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="py-2 px-3 text-left text-xs text-gray-500">Teklif No</th>
                    <th className="py-2 px-3 text-right text-xs text-gray-500">Indirim %</th>
                    <th className="py-2 px-3 text-right text-xs text-gray-500">Toplam</th>
                  </tr>
                </thead>
                <tbody>
                  {discounts.outliers.slice(0, 10).map((o: Record<string, unknown>) => (
                    <tr
                      key={o.id as number}
                      className="border-b border-gray-50 dark:border-gray-800"
                    >
                      <td className="py-2 px-3 font-mono text-xs">{o.quote_number as string}</td>
                      <td className="py-2 px-3 text-right text-red-600 font-semibold">
                        %{o.discount_rate as number}
                      </td>
                      <td className="py-2 px-3 text-right">
                        {formatCurrency(o.grand_total as number, 'TRY')}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {sla?.breaches && sla.breaches.length > 0 && (
          <Card title="SLA Ihlalleri">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="py-2 px-3 text-left text-xs text-gray-500">Gonderen</th>
                    <th className="py-2 px-3 text-left text-xs text-gray-500">Konu</th>
                    <th className="py-2 px-3 text-right text-xs text-gray-500">Yanit (dk)</th>
                  </tr>
                </thead>
                <tbody>
                  {sla.breaches.slice(0, 10).map((b: Record<string, unknown>, i: number) => (
                    <tr key={i} className="border-b border-gray-50 dark:border-gray-800">
                      <td className="py-2 px-3 text-xs">{b.from_address as string}</td>
                      <td className="py-2 px-3 text-xs truncate max-w-[200px]">
                        {b.subject as string}
                      </td>
                      <td className="py-2 px-3 text-right text-red-600 font-semibold">
                        {b.response_minutes as number}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </div>

      {/* Revenue Waterfall (Modul 5) */}
      <Card
        title="Gelir Selalesi"
        className="mb-6 mt-6"
        action={
          <select
            value={waterfallPeriod}
            onChange={(e) => setWaterfallPeriod(e.target.value)}
            className="rounded-lg border border-gray-200 bg-white px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
          >
            <option value="this_month">Bu Ay</option>
            <option value="last_month">Gecen Ay</option>
            <option value="this_quarter">Bu Ceyrek</option>
          </select>
        }
      >
        {waterfall ? (
          <div>
            <div className="h-[280px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={waterfall.categories.map((c) => ({
                    label: c.label,
                    amount: c.positive ? c.amount : -c.amount,
                    count: c.count,
                    positive: c.positive,
                  }))}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="label" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    formatter={(value) => formatCurrency(Math.abs(Number(value)), 'TRY')}
                    labelFormatter={(label) => String(label)}
                  />
                  <ReferenceLine y={0} stroke="#9ca3af" />
                  <Bar dataKey="amount" radius={[6, 6, 0, 0]}>
                    {waterfall.categories.map((c, i) => (
                      <Cell key={`cell-${i}`} fill={c.positive ? '#22c55e' : '#ef4444'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="mt-4 flex items-center justify-between border-t border-gray-200 pt-3 dark:border-gray-700">
              <div className="space-y-1">
                {waterfall.categories.map((c) => (
                  <div key={c.type} className="flex items-center gap-2 text-sm">
                    <span
                      className={`inline-block h-2 w-2 rounded-full ${c.positive ? 'bg-green-500' : 'bg-red-500'}`}
                    />
                    <span className="text-gray-600 dark:text-gray-400">{c.label}:</span>
                    <span className="font-semibold text-gray-900 dark:text-white">
                      {c.count} adet - {formatCurrency(c.amount, 'TRY')}
                    </span>
                  </div>
                ))}
              </div>
              <div className="text-right">
                <p className="text-xs text-gray-500 dark:text-gray-400">Net Degisim</p>
                <p
                  className={`text-xl font-bold ${waterfall.net_change >= 0 ? 'text-green-600' : 'text-red-600'}`}
                >
                  {waterfall.net_change >= 0 ? '+' : ''}
                  {formatCurrency(waterfall.net_change, 'TRY')}
                </p>
              </div>
            </div>
          </div>
        ) : (
          <Skeleton variant="card" />
        )}
      </Card>

      {/* Revenue Leak Trend (Modul 10) */}
      {leaks && leaks.items.length > 0 && (
        <Card title="Gelir Sizintisi Trendi" className="mb-6">
          <div className="mb-4 flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500 dark:text-gray-400">
                Toplam Sizinti Tutari:
              </span>
              <span className="text-lg font-bold text-red-600">
                {formatCurrency(leaks.total_leak_amount, 'TRY')}
              </span>
            </div>
            <Badge variant="danger">{leaks.total_leaks} firsat</Badge>
          </div>
          <div className="space-y-3">
            {leaks.items.map((item: RevenueLeakItem) => (
              <button
                key={item.opportunity_id}
                type="button"
                onClick={() => navigate(`/opportunities/${item.opportunity_id}`)}
                className="flex w-full items-start justify-between rounded-lg border border-gray-100 p-3 hover:bg-gray-50 dark:border-gray-700 dark:hover:bg-gray-800 transition-colors"
              >
                <div className="min-w-0 flex-1 text-left">
                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                    {item.title}
                  </p>
                  <p className="text-xs text-gray-400 mt-0.5">
                    {item.owner_name} - {item.stage}
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {item.factors.map((f) => (
                      <Badge key={f.name} variant="warning" size="sm">
                        {f.label}: {f.detail}
                      </Badge>
                    ))}
                  </div>
                </div>
                <div className="ml-3 flex flex-col items-end gap-1">
                  <span className="text-sm font-bold text-gray-900 dark:text-white">
                    {formatCurrency(item.amount, 'TRY')}
                  </span>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs text-gray-500">Sizinti Skoru:</span>
                    <span
                      className={`text-sm font-bold ${item.leak_score >= 50 ? 'text-red-600' : 'text-amber-600'}`}
                    >
                      {item.leak_score}
                    </span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
