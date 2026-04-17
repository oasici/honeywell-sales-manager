import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Trophy, Award } from 'lucide-react';
import { leaderboardApi } from '../../lib/api';

import type { LeaderboardEntry, Achievement } from '../../lib/types';

const PERIOD_OPTIONS = [
  { value: 'week', label: 'Hafta' },
  { value: 'month', label: 'Ay' },
  { value: 'quarter', label: 'Ceyrek' },
  { value: 'year', label: 'Yil' },
];

const METRIC_OPTIONS = [
  { value: 'revenue', label: 'Gelir' },
  { value: 'deals_won', label: 'Kazanilan' },
  { value: 'activities', label: 'Aktivite' },
  { value: 'response_time', label: 'Cevap Süresi' },
];

const RANK_COLORS: Record<number, string> = {
  1: 'bg-yellow-50 border-yellow-300',
  2: 'bg-gray-50 border-gray-300',
  3: 'bg-orange-50 border-orange-300',
};

export default function LeaderboardPage() {
  const [period, setPeriod] = useState('month');
  const [metric, setMetric] = useState('revenue');
  const [selectedUserId, setSelectedUserId] = useState<number | null>(null);

  const { data: leaderboardData, isLoading } = useQuery<{ data: LeaderboardEntry[] }>({
    queryKey: ['leaderboard', period, metric],
    queryFn: () => leaderboardApi.getLeaderboard(period, metric),
  });

  const { data: achievementsData } = useQuery<{ data: Achievement[] }>({
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
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Trophy size={24} className="text-honeywell-red" />
        <h1 className="text-2xl font-bold text-gray-900">Sıralama</h1>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="flex items-center gap-2">
          <label htmlFor="period-select" className="text-sm font-medium text-gray-600">
            Donem:
          </label>
          <select
            id="period-select"
            value={period}
            onChange={(e) => setPeriod(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-honeywell-red focus:outline-none"
          >
            {PERIOD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="metric-select" className="text-sm font-medium text-gray-600">
            Metrik:
          </label>
          <select
            id="metric-select"
            value={metric}
            onChange={(e) => setMetric(e.target.value)}
            className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-honeywell-red focus:outline-none"
          >
            {METRIC_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Leaderboard Table */}
      <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 bg-gray-50">
                <th className="px-4 py-3 text-left font-semibold text-gray-600">Sira</th>
                <th className="px-4 py-3 text-left font-semibold text-gray-600">Temsilci</th>
                <th className="px-4 py-3 text-right font-semibold text-gray-600">Değer</th>
                <th className="px-4 py-3 text-right font-semibold text-gray-600">Degisim</th>
                <th className="px-4 py-3 text-center font-semibold text-gray-600">Rozetler</th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                    Yükleniyor...
                  </td>
                </tr>
              ) : rankings.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-8 text-center text-gray-400">
                    Henüz veri yok
                  </td>
                </tr>
              ) : (
                rankings.map((entry) => (
                  <tr
                    key={entry.user_id}
                    className={`border-b border-gray-100 transition-colors hover:bg-gray-50 ${
                      RANK_COLORS[entry.rank] ?? ''
                    } ${selectedUserId === entry.user_id ? 'ring-2 ring-honeywell-red/30' : ''}`}
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
                      <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-gray-200 text-xs font-bold">
                        {entry.rank}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-honeywell-red/10 text-xs font-bold text-honeywell-red">
                          {entry.user_name
                            .split(' ')
                            .map((n) => n[0])
                            .join('')
                            .toUpperCase()
                            .slice(0, 2)}
                        </div>
                        <span className="font-medium text-gray-900">{entry.user_name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3 text-right font-semibold text-gray-900">
                      {formatValue(entry.value, metric)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <DeltaBadge delta={entry.delta_vs_prev_period} metric={metric} />
                    </td>
                    <td className="px-4 py-3 text-center">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedUserId(entry.user_id);
                        }}
                        className="text-xs text-honeywell-red hover:underline"
                      >
                        Gor
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Achievement Section */}
      {selectedUserId && (
        <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
          <div className="mb-4 flex items-center gap-2">
            <Award size={18} className="text-honeywell-red" />
            <h2 className="text-lg font-semibold text-gray-900">Kazanilan Rozetler</h2>
          </div>
          {achievements.length === 0 ? (
            <p className="text-sm text-gray-400">Henüz rozet kazanilmamis</p>
          ) : (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
              {achievements.map((ach) => (
                <div
                  key={ach.id}
                  className="flex flex-col items-center rounded-lg border border-gray-200 bg-gray-50 p-3 text-center"
                >
                  <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-honeywell-red/10">
                    <Trophy size={18} className="text-honeywell-red" />
                  </div>
                  <p className="text-xs font-semibold text-gray-800">{ach.title}</p>
                  <p className="mt-0.5 text-[10px] text-gray-400">
                    {ach.earned_at ? new Date(ach.earned_at).toLocaleDateString('tr-TR') : ''}
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
    return <span className="text-xs text-gray-400">-</span>;
  }
  const isPositive = metric === 'response_time' ? delta < 0 : delta > 0;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
        isPositive ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
      }`}
    >
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
