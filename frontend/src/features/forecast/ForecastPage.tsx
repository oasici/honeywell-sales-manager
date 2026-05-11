import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  LineChart,
  Line,
} from 'recharts';
import { TrendingUp, TrendingDown, Target, Activity } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { forecastApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import { useT } from '../../hooks/useT';

/**
 * S-A — Forecasting standalone page.
 *
 * Composes the existing `forecastApi` (legacy stage-weighted + hybrid
 * predictive) into a single manager-facing rollup view: commit / best /
 * worst, by-stage breakdown, week-over-week movement, and accuracy.
 */
export default function ForecastPage() {
  const t = useT();
  const [period] = useState<'this_quarter'>('this_quarter');

  const hybridQuery = useQuery({
    queryKey: ['forecast', 'hybrid', period],
    queryFn: () => forecastApi.getHybrid(),
  });

  const wowQuery = useQuery({
    queryKey: ['forecast', 'wow', 8],
    queryFn: () => forecastApi.getWoW(8),
  });

  const accuracyQuery = useQuery({
    queryKey: ['forecast', 'accuracy'],
    queryFn: () => forecastApi.getAccuracy(),
  });

  const teamQuery = useQuery({
    queryKey: ['forecast', 'team-rollup'],
    queryFn: () => forecastApi.getTeamRollup(),
  });

  const hybrid = hybridQuery.data as
    | {
        legacy_weighted_total: number;
        hybrid_weighted_total: number;
        by_stage: Array<{
          stage: string;
          count: number;
          amount: number;
          legacy_weighted: number;
          hybrid_weighted: number;
        }>;
        by_confidence: Record<string, { count: number; amount: number; hybrid_weighted: number }>;
      }
    | undefined;

  const wow = wowQuery.data as
    | {
        weeks: Array<{ week_label: string; total: number }>;
        current_total: number;
        previous_total: number;
        delta: number;
        delta_pct: number;
      }
    | undefined;

  const accuracy = accuracyQuery.data as
    | {
        period: string;
        commit_forecast: number;
        actual_won: number;
        accuracy_pct: number;
        per_rep: Array<{
          user_id: number;
          user_name: string;
          forecast: number;
          actual: number;
          accuracy: number;
        }>;
      }
    | undefined;

  const team = teamQuery.data as
    | { reps: Array<{ rep_id: number; rep_name: string; pipeline: number; weighted: number }> }
    | undefined;

  const isLoading =
    hybridQuery.isLoading || wowQuery.isLoading || accuracyQuery.isLoading || teamQuery.isLoading;

  const commit = hybrid?.hybrid_weighted_total ?? 0;
  const legacy = hybrid?.legacy_weighted_total ?? 0;
  // Round-10 R10-FE-1 — operator precedence bug. `??` binds looser than
  // `+`, so the unparenthesised form silently collapsed to
  // `high?.amount ?? medium?.amount ?? 0` and the medium bucket never
  // contributed to best-case. Sales managers saw a depressed forecast.
  const bestCase =
    (hybrid?.by_confidence?.high?.amount ?? 0) +
    (hybrid?.by_confidence?.medium?.amount ?? 0);
  const worstCase = hybrid?.by_confidence?.high?.hybrid_weighted ?? 0;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Forecast"
        description="Commit / best-case / worst-case rollup across the active pipeline"
      />

      {isLoading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28" />
          ))}
        </div>
      )}

      {!isLoading && hybrid && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
          <Card>
            <div className="flex items-center justify-between">
              <span className="text-caption text-slate-500">Commit (predictive)</span>
              <Target className="h-4 w-4 text-honeywell-red" />
            </div>
            <div className="mt-2 text-heading-2 tabular-nums">{formatCurrency(commit)}</div>
            <div className="mt-1 text-caption text-slate-400">
              {t('forecast.hybrid_subtitle')}
            </div>
          </Card>
          <Card>
            <div className="flex items-center justify-between">
              <span className="text-caption text-slate-500">Legacy (stage-weighted)</span>
              <Activity className="h-4 w-4 text-slate-400" />
            </div>
            <div className="mt-2 text-heading-2 tabular-nums">{formatCurrency(legacy)}</div>
            <div className="mt-1 text-caption text-slate-400">Eski stage-probability ağırlıklı</div>
          </Card>
          <Card>
            <div className="flex items-center justify-between">
              <span className="text-caption text-slate-500">Best case</span>
              <TrendingUp className="h-4 w-4 text-success" />
            </div>
            <div className="mt-2 text-heading-2 tabular-nums">{formatCurrency(bestCase)}</div>
            <div className="mt-1 text-caption text-slate-400">High + medium confidence</div>
          </Card>
          <Card>
            <div className="flex items-center justify-between">
              <span className="text-caption text-slate-500">Most likely worst</span>
              <TrendingDown className="h-4 w-4 text-warning" />
            </div>
            <div className="mt-2 text-heading-2 tabular-nums">{formatCurrency(worstCase)}</div>
            <div className="mt-1 text-caption text-slate-400">High confidence only</div>
          </Card>
        </div>
      )}

      {wow && wow.weeks.length > 0 && (
        <Card title="Hafta-üzeri-hafta hareket" description="Pipeline toplamı">
          <div className="mt-4 flex items-center gap-4">
            <div className="text-heading-3 tabular-nums">{formatCurrency(wow.current_total)}</div>
            <Badge variant={wow.delta >= 0 ? 'success' : 'danger'}>
              {wow.delta >= 0 ? '+' : ''}
              {formatCurrency(wow.delta)} ({wow.delta_pct.toFixed(1)}%)
            </Badge>
          </div>
          <div className="mt-4 h-56">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={wow.weeks}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                <XAxis dataKey="week_label" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => formatCurrency(v as number)} />
                <Tooltip formatter={(v) => formatCurrency(Number(v ?? 0))} />
                <Line
                  type="monotone"
                  dataKey="total"
                  stroke="var(--color-honeywell-red)"
                  strokeWidth={2}
                  dot={{ r: 3 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {hybrid && hybrid.by_stage.length > 0 && (
        <Card title="Stage-üzeri kırılım" description="Legacy ağırlıklı vs. predictive ağırlıklı">
          <div className="mt-4 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={hybrid.by_stage}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
                <XAxis dataKey="stage" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => formatCurrency(v as number)} />
                <Tooltip formatter={(v) => formatCurrency(Number(v ?? 0))} />
                <Bar dataKey="legacy_weighted" fill="var(--color-honeywell-light)" name="Legacy" />
                <Bar
                  dataKey="hybrid_weighted"
                  fill="var(--color-honeywell-red)"
                  name="Predictive"
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {accuracy && (
        <Card
          title="Forecast doğruluğu"
          description={`${accuracy.period} · ${accuracy.accuracy_pct.toFixed(1)}%`}
        >
          {accuracy.per_rep.length === 0 ? (
            <EmptyState title="Henüz kapanan fırsat yok" variant="compact" />
          ) : (
            <table className="mt-3 w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100 text-overline text-slate-500">
                  <th className="px-3 py-2 text-left">Rep</th>
                  <th className="px-3 py-2 text-right">Forecast</th>
                  <th className="px-3 py-2 text-right">Actual</th>
                  <th className="px-3 py-2 text-right">Doğruluk</th>
                </tr>
              </thead>
              <tbody>
                {accuracy.per_rep.map((row) => (
                  <tr key={row.user_id} className="border-b border-slate-100">
                    <td className="px-3 py-2 text-slate-700">
                      {row.user_name || `User ${row.user_id}`}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {formatCurrency(row.forecast)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {formatCurrency(row.actual)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Badge
                        variant={
                          row.accuracy >= 80 ? 'success' : row.accuracy >= 60 ? 'warning' : 'danger'
                        }
                      >
                        {row.accuracy.toFixed(1)}%
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      )}

      {team && team.reps && team.reps.length > 0 && (
        <Card title="Rep rollup" description="Temsilci başına pipeline">
          <table className="mt-3 w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 text-overline text-slate-500">
                <th className="px-3 py-2 text-left">Rep</th>
                <th className="px-3 py-2 text-right">Pipeline</th>
                <th className="px-3 py-2 text-right">Weighted</th>
              </tr>
            </thead>
            <tbody>
              {team.reps.map((row) => (
                <tr key={row.rep_id} className="border-b border-slate-100">
                  <td className="px-3 py-2 text-slate-700">{row.rep_name}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatCurrency(row.pipeline)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatCurrency(row.weighted)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
