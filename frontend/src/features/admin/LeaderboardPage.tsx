import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Trophy, Award, ArrowUp, ArrowDown, Minus } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { leaderboardApi } from '../../lib/api';
import { formatDate } from '../../lib/formatters';
import { useT } from '../../hooks/useT';

import type { LeaderboardEntry, Achievement } from '../../lib/types';

const PERIOD_OPTIONS = [
  { value: 'week', label: 'Hafta' },
  { value: 'month', label: 'Ay' },
  { value: 'quarter', label: 'Çeyrek' },
  { value: 'year', label: 'Yıl' },
];

const METRIC_OPTIONS = [
  { value: 'revenue', label: 'Gelir' },
  { value: 'deals_won', label: 'Kazanılan' },
  { value: 'activities', label: 'Aktivite' },
  { value: 'response_time', label: 'Cevap Süresi' },
];

/**
 * Rank tone — 1st gold, 2nd silver, 3rd bronze. Subtle so the row stays
 * scannable; the numeral pill carries the tint, not the row background.
 */
const PODIUM_TONE: Record<number, string> = {
  1: 'bg-amber-50 text-amber-800 ring-amber-100 dark:bg-amber-950/30 dark:text-amber-300 dark:ring-amber-900/40',
  2: 'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700',
  3: 'bg-orange-50 text-orange-800 ring-orange-100 dark:bg-orange-950/30 dark:text-orange-300 dark:ring-orange-900/40',
};

export default function LeaderboardPage() {
  const t = useT();
  const [period, setPeriod] = useState('month');
  const [metric, setMetric] = useState('revenue');
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);

  // Round-14 Sprint 14e — surface isError on both queries so the
  // leaderboard panel and badge column show a retry banner instead of
  // rendering blank when the backend is unavailable.
  const {
    data: leaderboardData,
    isLoading,
    isError: leaderboardIsError,
    refetch: refetchLeaderboard,
  } = useQuery<{ data: LeaderboardEntry[] }>({
    queryKey: ['leaderboard', period, metric],
    queryFn: () => leaderboardApi.getLeaderboard(period, metric),
  });

  const {
    data: achievementsData,
    isError: achievementsIsError,
    refetch: refetchAchievements,
  } = useQuery<{ data: Achievement[] }>({
    queryKey: ['achievements', selectedUserId],
    queryFn: () =>
      selectedUserId
        ? leaderboardApi.getUserAchievements(selectedUserId)
        : leaderboardApi.getAchievements(),
    enabled: selectedUserId !== null || true,
  });

  const rankings = leaderboardData?.data ?? [];
  const achievements = achievementsData?.data ?? [];

  return (
    <div>
      <PageHeader title="Sıralama" description="Ekip performansı, rozetler ve dönemsel başarı" />

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-44">
          <Select
            label="Dönem"
            options={PERIOD_OPTIONS}
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
          />
        </div>
        <div className="w-52">
          <Select
            label="Metrik"
            options={METRIC_OPTIONS}
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
          />
        </div>
      </div>

      {/* Leaderboard table */}
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-900/40">
                <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">Sıra</th>
                <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                  Temsilci
                </th>
                <th className="px-4 py-3 text-right text-overline text-slate-500 dark:text-slate-400">
                  Değer
                </th>
                {/* R6-RESP-1 — change + badges columns collapse on mobile. */}
                <th className="hidden px-4 py-3 text-right text-overline text-slate-500 sm:table-cell dark:text-slate-400">
                  Değişim
                </th>
                <th className="hidden px-4 py-3 text-center text-overline text-slate-500 md:table-cell dark:text-slate-400">
                  Rozetler
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {isLoading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-3">
                    <Skeleton variant="line" count={3} />
                  </td>
                </tr>
              ) : leaderboardIsError ? (
                <tr>
                  <td colSpan={5} className="px-4 py-3">
                    <QueryErrorBanner onRetry={() => refetchLeaderboard()} />
                  </td>
                </tr>
              ) : rankings.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <EmptyState
                      variant="compact"
                      icon={<Trophy size={18} />}
                      title={t('common.no_data')}
                    />
                  </td>
                </tr>
              ) : (
                rankings.map((entry) => (
                  <tr
                    key={entry.user_id}
                    className={[
                      'cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40',
                      selectedUserId === entry.user_id
                        ? 'bg-honeywell-red/4 ring-2 ring-inset ring-honeywell-red/30'
                        : '',
                    ].join(' ')}
                    onClick={() => setSelectedUserId(entry.user_id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        setSelectedUserId(entry.user_id);
                      }
                    }}
                  >
                    <td className="px-4 py-3">
                      <span
                        className={[
                          'inline-flex h-7 min-w-[28px] items-center justify-center rounded-full text-[12px] font-bold tabular-nums ring-1 ring-inset',
                          PODIUM_TONE[entry.rank] ??
                            'bg-slate-50 text-slate-500 ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-700',
                        ].join(' ')}
                      >
                        {entry.rank}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-honeywell-red/10 text-[12px] font-semibold text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                          {entry.user_name
                            .split(' ')
                            .map((n) => n[0])
                            .join('')
                            .toUpperCase()
                            .slice(0, 2)}
                        </span>
                        <span className="text-[13px] font-medium text-slate-900 dark:text-white">
                          {entry.user_name}
                        </span>
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right text-[13px] font-semibold tabular-nums text-slate-900 dark:text-white">
                      {formatValue(entry.value, metric)}
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-3 text-right sm:table-cell">
                      <DeltaBadge delta={entry.delta_vs_prev_period} metric={metric} />
                    </td>
                    <td className="hidden px-4 py-3 text-center md:table-cell">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedUserId(entry.user_id);
                        }}
                        className="text-[12px] font-medium text-honeywell-red transition-colors hover:underline"
                      >
                        Gör
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Achievement panel */}
      {selectedUserId && (
        <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <div className="mb-4 flex items-center gap-2.5">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-[10px] bg-amber-100 text-amber-700 ring-1 ring-inset ring-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-900/60">
              <Award size={14} />
            </span>
            <h2 className="text-heading-3 text-slate-900 dark:text-white">Kazanılan Rozetler</h2>
          </div>
          {achievementsIsError ? (
            <QueryErrorBanner onRetry={() => refetchAchievements()} />
          ) : achievements.length === 0 ? (
            <p className="text-[13px] text-slate-400">{t('common.no_badges')}</p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
              {achievements.map((ach) => (
                <div
                  key={ach.id}
                  className="flex flex-col items-center rounded-xl border border-slate-200 bg-slate-50/60 p-3 text-center dark:border-slate-800 dark:bg-slate-900/40"
                >
                  <span className="mb-2 inline-flex h-10 w-10 items-center justify-center rounded-[12px] bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                    <Trophy size={16} />
                  </span>
                  <p className="text-[12px] font-semibold text-slate-800 dark:text-slate-100">
                    {ach.title}
                  </p>
                  <p className="mt-0.5 text-[10px] tabular-nums text-slate-400 dark:text-slate-500">
                    {ach.earned_at ? formatDate(ach.earned_at) : ''}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function DeltaBadge({ delta, metric }: { delta: number; metric: string }) {
  if (delta === 0) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] tabular-nums text-slate-400">
        <Minus size={11} />—
      </span>
    );
  }
  const isPositive = metric === 'response_time' ? delta < 0 : delta > 0;
  return (
    <span
      className={[
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold tabular-nums ring-1 ring-inset',
        isPositive
          ? 'bg-emerald-50 text-emerald-700 ring-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-400 dark:ring-emerald-900/40'
          : 'bg-red-50 text-red-700 ring-red-100 dark:bg-red-950/30 dark:text-red-400 dark:ring-red-900/40',
      ].join(' ')}
    >
      {delta > 0 ? <ArrowUp size={11} /> : <ArrowDown size={11} />}
      {delta > 0 ? '+' : ''}
      {formatValue(delta, metric)}
    </span>
  );
}

function formatValue(value: number, metric: string): string {
  if (metric === 'revenue') {
    if (Math.abs(value) >= 1000) {
      return `${(value / 1000).toFixed(1)}K`;
    }
    return value.toLocaleString('tr-TR');
  }
  if (metric === 'response_time') {
    return `${value} sa`;
  }
  return String(value);
}
