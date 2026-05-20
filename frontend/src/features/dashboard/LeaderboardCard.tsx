import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Trophy, ArrowDown, ArrowUp, Minus } from 'lucide-react';
import { leaderboardApi } from '../../lib/api';
import { Button } from '../../components/ui/Button';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { useT } from '../../hooks/useT';

import type { LeaderboardEntry } from '../../lib/types';

const METRIC_OPTIONS = [
  { value: 'revenue', label: 'Gelir' },
  { value: 'deals_won', label: 'Kazanılan' },
  { value: 'activities', label: 'Aktivite' },
  { value: 'response_time', label: 'Cevap Süresi' },
];

/**
 * Podium tone: rank 1 (gold), 2 (silver), 3 (bronze) — kept *very* subtle to
 * sit inside a card without screaming "achievement page". The numeral pill
 * carries the tint; the row itself stays neutral.
 */
const PODIUM_TONE: Array<{ pill: string; numeral: string }> = [
  { pill: 'bg-amber-50 text-amber-800 ring-amber-100', numeral: 'text-amber-600' },
  { pill: 'bg-slate-100 text-slate-700 ring-slate-200', numeral: 'text-slate-500' },
  { pill: 'bg-orange-50 text-orange-800 ring-orange-100', numeral: 'text-orange-600' },
];

const TOP_COUNT = 3;

export function LeaderboardCard() {
  const t = useT();
  const navigate = useNavigate();
  const [metric, setMetric] = useState('revenue');

  const { data, isError, refetch } = useQuery<{ data: LeaderboardEntry[] }>({
    queryKey: ['leaderboard-card', metric],
    queryFn: () => leaderboardApi.getLeaderboard('month', metric),
    refetchInterval: 120_000,
  });

  const topThree = data?.data?.slice(0, TOP_COUNT) ?? [];

  return (
    <div className="rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center justify-between px-5 pb-3 pt-5">
        <h3 className="flex items-center gap-2 text-overline text-slate-500 dark:text-slate-400">
          <Trophy size={14} className="text-amber-500" />
          Sıralama
        </h3>
        <select
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
          aria-label="Metrik seçimi"
          className="h-7 rounded-[8px] border border-slate-200 bg-white px-2 text-[12px] font-medium text-slate-700 transition-colors focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200"
        >
          {METRIC_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {isError ? (
        <div className="px-5 pb-5">
          <QueryErrorBanner variant="block" onRetry={() => refetch()} />
        </div>
      ) : topThree.length === 0 ? (
        <p className="px-5 pb-5 text-[13px] text-slate-400">{t('common.no_data')}</p>
      ) : (
        <ul className="divide-y divide-slate-100 px-2 dark:divide-slate-800">
          {topThree.map((entry, idx) => {
            // Round-10 R10-FE-13 — topThree is sliced to TOP_COUNT (3) and
            // PODIUM_TONE has 3 entries, so this index is always in-range.
            const tone = PODIUM_TONE[idx] ?? PODIUM_TONE[0]!;
            const initials = entry.user_name
              .split(' ')
              .map((n) => n[0])
              .join('')
              .toUpperCase()
              .slice(0, 2);
            const delta = entry.delta_vs_prev_period;
            return (
              <li
                key={entry.user_id}
                className="flex items-center gap-3 rounded-xl px-3 py-2.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
              >
                <span
                  className={[
                    'inline-flex h-7 w-7 items-center justify-center rounded-full text-[12px] font-bold ring-1 ring-inset',
                    tone.pill,
                  ].join(' ')}
                >
                  {idx + 1}
                </span>
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-[11px] font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                  {initials}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-slate-900 dark:text-white">
                    {entry.user_name}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[13px] font-semibold tabular-nums text-slate-900 dark:text-white">
                    {formatValue(entry.value, metric)}
                  </p>
                  <p
                    className={[
                      'mt-0.5 flex items-center justify-end gap-0.5 text-[11px] font-medium tabular-nums',
                      delta > 0
                        ? 'text-emerald-600'
                        : delta < 0
                          ? 'text-red-600'
                          : 'text-slate-400',
                    ].join(' ')}
                  >
                    {delta > 0 ? (
                      <ArrowUp size={11} />
                    ) : delta < 0 ? (
                      <ArrowDown size={11} />
                    ) : (
                      <Minus size={11} />
                    )}
                    {delta === 0 ? '—' : formatValue(Math.abs(delta), metric)}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <div className="border-t border-slate-100 px-3 py-2 dark:border-slate-800">
        <Button
          variant="tertiary"
          size="sm"
          onClick={() => navigate('/leaderboard')}
          className="w-full justify-center"
        >
          Tam Liste
        </Button>
      </div>
    </div>
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

export default LeaderboardCard;
