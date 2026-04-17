import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Trophy } from 'lucide-react';
import { leaderboardApi } from '../../lib/api';

import type { LeaderboardEntry } from '../../lib/types';

const METRIC_OPTIONS = [
  { value: 'revenue', label: 'Gelir' },
  { value: 'deals_won', label: 'Kazanilan' },
  { value: 'activities', label: 'Aktivite' },
  { value: 'response_time', label: 'Cevap Süresi' },
];

const PODIUM_COLORS = [
  'bg-yellow-100 text-yellow-800 border-yellow-300',
  'bg-gray-100 text-gray-700 border-gray-300',
  'bg-orange-100 text-orange-800 border-orange-300',
];

const PODIUM_LABELS = ['1.', '2.', '3.'];

const TOP_COUNT = 3;

export function LeaderboardCard() {
  const navigate = useNavigate();
  const [metric, setMetric] = useState('revenue');

  const { data } = useQuery<{ data: LeaderboardEntry[] }>({
    queryKey: ['leaderboard-card', metric],
    queryFn: () => leaderboardApi.getLeaderboard('month', metric),
    refetchInterval: 120_000,
  });

  const topThree = data?.data?.slice(0, TOP_COUNT) ?? [];

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-gray-500">
          <Trophy size={16} />
          Sıralama
        </h3>
        <select
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
          className="rounded-md border border-gray-300 px-2 py-1 text-xs text-gray-600 focus:border-honeywell-red focus:outline-none"
          aria-label="Metrik secimi"
        >
          {METRIC_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {topThree.length === 0 ? (
        <p className="text-sm text-gray-400">Henüz veri yok</p>
      ) : (
        <div className="space-y-2">
          {topThree.map((entry, idx) => (
            <div
              key={entry.user_id}
              className={`flex items-center gap-3 rounded-lg border px-3 py-2 ${PODIUM_COLORS[idx]}`}
            >
              <span className="text-sm font-bold">{PODIUM_LABELS[idx]}</span>
              <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/60 text-xs font-bold">
                {entry.user_name
                  .split(' ')
                  .map((n) => n[0])
                  .join('')
                  .toUpperCase()
                  .slice(0, 2)}
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{entry.user_name}</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-bold">{formatValue(entry.value, metric)}</p>
                {entry.delta_vs_prev_period !== 0 && (
                  <p
                    className={`text-xs ${
                      entry.delta_vs_prev_period > 0 ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    {entry.delta_vs_prev_period > 0 ? '+' : ''}
                    {formatValue(entry.delta_vs_prev_period, metric)}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <button
        onClick={() => navigate('/leaderboard')}
        className="mt-3 w-full rounded-lg border border-gray-200 py-1.5 text-xs font-medium text-gray-500 transition-colors hover:bg-gray-50 hover:text-gray-700"
        type="button"
      >
        Tam Liste
      </button>
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
