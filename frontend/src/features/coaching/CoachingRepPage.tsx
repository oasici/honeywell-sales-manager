import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  Area, ComposedChart,
} from 'recharts';
import { ArrowUp, ArrowDown } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { coachingApi } from '../../lib/api';
import { formatPercent } from '../../lib/formatters';

import type {
  CoachingRepScore,
  CoachingSnapshot,
  CoachingBenchmark,
  CoachingOverview,
} from '../../lib/types';


const RISK_LABELS: Record<string, string> = {
  healthy: 'Saglikli',
  needs_improvement: 'Gelistirilmeli',
  at_risk: 'Risk Altinda',
};

const RISK_BADGE_VARIANT: Record<string, 'success' | 'warning' | 'danger'> = {
  healthy: 'success',
  needs_improvement: 'warning',
  at_risk: 'danger',
};

const SCORE_RING_RADIUS = 54;
const SCORE_RING_CIRCUMFERENCE = 2 * Math.PI * SCORE_RING_RADIUS;

function ScoreRing({ score }: { score: number }) {
  const pct = Math.min(score, 100);
  const offset = SCORE_RING_CIRCUMFERENCE - (pct / 100) * SCORE_RING_CIRCUMFERENCE;
  const color =
    score >= 70 ? '#22c55e' : score >= 40 ? '#f59e0b' : '#ef4444';

  return (
    <div className="relative h-32 w-32">
      <svg className="h-32 w-32 -rotate-90" viewBox="0 0 120 120">
        <circle
          cx="60"
          cy="60"
          r={SCORE_RING_RADIUS}
          stroke="#e5e7eb"
          strokeWidth="8"
          fill="none"
        />
        <circle
          cx="60"
          cy="60"
          r={SCORE_RING_RADIUS}
          stroke={color}
          strokeWidth="8"
          fill="none"
          strokeDasharray={SCORE_RING_CIRCUMFERENCE}
          strokeDashoffset={offset}
          strokeLinecap="round"
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        <span className="text-3xl font-bold text-gray-900 dark:text-white">
          {score}
        </span>
      </div>
    </div>
  );
}

function ProgressBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="h-2 w-full rounded-full bg-gray-200 dark:bg-gray-700">
      <div
        className="h-2 rounded-full bg-blue-500 transition-all duration-300"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function formatSnapshotDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('tr-TR', {
    day: '2-digit',
    month: '2-digit',
  });
}

function TrendChart({ snapshots }: { snapshots: CoachingSnapshot[] }) {
  if (snapshots.length === 0) {
    return <EmptyState title="Henüz trend verisi bulunmuyor" />;
  }

  const chartData = snapshots.map((snap) => ({
    date: formatSnapshotDate(snap.created_at),
    score: snap.score,
  }));

  const firstScore = snapshots[0].score;
  const lastScore = snapshots[snapshots.length - 1].score;
  const isUptrend = lastScore >= firstScore;
  const lineColor = isUptrend ? '#22c55e' : '#ef4444';

  return (
    <div className="h-[200px]">
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="date" tick={{ fontSize: 11 }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 11 }} />
          <Tooltip />
          <defs>
            <linearGradient id="scoreFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor={lineColor} stopOpacity={0.2} />
              <stop offset="95%" stopColor={lineColor} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="score"
            stroke="none"
            fill="url(#scoreFill)"
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke={lineColor}
            strokeWidth={2}
            dot={{ r: 4, fill: lineColor }}
            name="Skor"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function CoachingRepPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const userId = Number(id);

  const {
    data: rep,
    isLoading: isRepLoading,
  } = useQuery<CoachingRepScore>({
    queryKey: ['coaching', 'rep', userId],
    queryFn: () => coachingApi.getRepReport(userId),
    enabled: !!userId,
  });

  const {
    data: trendsData,
    isLoading: isTrendsLoading,
  } = useQuery<{ user_id: number; snapshots: CoachingSnapshot[]; total: number }>({
    queryKey: ['coaching', 'rep', userId, 'trends'],
    queryFn: () => coachingApi.getRepTrends(userId),
    enabled: !!userId,
  });

  const {
    data: benchmarksData,
    isLoading: isBenchmarksLoading,
  } = useQuery<{ benchmarks: CoachingBenchmark[]; total: number }>({
    queryKey: ['coaching', 'benchmarks'],
    queryFn: () => coachingApi.getBenchmarks(),
  });

  const { data: overview } = useQuery<CoachingOverview>({
    queryKey: ['coaching', 'overview'],
    queryFn: () => coachingApi.getOverview(),
  });

  if (isRepLoading) return <Skeleton variant="card" count={3} />;

  if (!rep) {
    return (
      <div className="p-8 text-center text-gray-500">
        Temsilci bulunamadi
      </div>
    );
  }

  const snapshots = trendsData?.snapshots ?? [];
  const benchmarks = benchmarksData?.benchmarks ?? [];
  const currentBenchmark = benchmarks.find((b) => b.user_id === userId);

  return (
    <div className="space-y-6">
      <PageHeader
        title={rep.user_name}
        description="Temsilci performans detayi ve koçluk raporu"
      >
        <Button variant="secondary" onClick={() => navigate('/coaching')}>
          Geri
        </Button>
      </PageHeader>

      {/* Score and Risk Level */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Performans Skoru">
          <div className="flex flex-col items-center gap-3 py-4">
            <ScoreRing score={rep.score} />
            <Badge
              variant={RISK_BADGE_VARIANT[rep.risk_level] || 'default'}
              size="md"
            >
              {RISK_LABELS[rep.risk_level] || rep.risk_level}
            </Badge>
          </div>
        </Card>

        {/* Comparison Stats + Indicators */}
        <div className="lg:col-span-2 space-y-4">
          {/* Team Average Comparison */}
          {overview?.summary && (
            <Card>
              <div className="flex items-center justify-between p-4">
                <div className="flex items-center gap-6">
                  <div className="text-center">
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Takim Ort
                    </p>
                    <p className="text-xl font-bold text-gray-900 dark:text-white">
                      {overview.summary.avg_score}
                    </p>
                  </div>
                  <div className="text-center">
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Bu Temsilci
                    </p>
                    <p className="text-xl font-bold text-gray-900 dark:text-white">
                      {rep.score}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  {rep.score > overview.summary.avg_score ? (
                    <>
                      <ArrowUp size={20} className="text-green-600" />
                      <span className="text-sm font-semibold text-green-600">
                        +{rep.score - overview.summary.avg_score} puan
                      </span>
                    </>
                  ) : rep.score < overview.summary.avg_score ? (
                    <>
                      <ArrowDown size={20} className="text-red-600" />
                      <span className="text-sm font-semibold text-red-600">
                        {rep.score - overview.summary.avg_score} puan
                      </span>
                    </>
                  ) : (
                    <span className="text-sm font-semibold text-gray-500">
                      Esit
                    </span>
                  )}
                </div>
              </div>
            </Card>
          )}

        {/* Indicators Table */}
        <Card title="Gostergeler">
          {rep.indicators.length === 0 ? (
            <EmptyState title="Gösterge verisi bulunmuyor" />
          ) : (
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {rep.indicators.map((indicator) => (
                <div
                  key={indicator.name}
                  className="flex items-center gap-4 px-4 py-3"
                >
                  <div className="min-w-[120px]">
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {indicator.label}
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      Agirlik: {formatPercent(indicator.weight)}
                    </p>
                  </div>
                  <div className="flex-1">
                    <ProgressBar value={indicator.score} />
                  </div>
                  <span className="min-w-[40px] text-right text-sm font-semibold text-gray-900 dark:text-white">
                    {indicator.score}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
        </div>
      </div>

      {/* Recommendations */}
      <Card title="Öneriler">
        {rep.recommendations.length === 0 ? (
          <EmptyState title="Henüz öneri bulunmuyor" />
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-gray-700">
            {rep.recommendations.map((rec, idx) => (
              <li
                key={idx}
                className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300"
              >
                {rec}
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Trend Chart */}
      <Card title="Skor Trendi">
        {isTrendsLoading ? (
          <Skeleton variant="card" count={1} />
        ) : (
          <div className="p-4">
            <TrendChart snapshots={snapshots} />
          </div>
        )}
      </Card>

      {/* Benchmarks */}
      <Card title="Karsilastirma (Benchmark)">
        {isBenchmarksLoading ? (
          <Skeleton variant="card" count={1} />
        ) : benchmarks.length === 0 ? (
          <EmptyState title="Benchmark verisi bulunmuyor" />
        ) : (
          <div className="space-y-4 p-4">
            {/* Current rep highlight */}
            {currentBenchmark && (
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-4 dark:border-blue-800 dark:bg-blue-900/20">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm font-medium text-blue-900 dark:text-blue-200">
                      {currentBenchmark.user_name} (Bu Temsilci)
                    </p>
                    <p className="text-xs text-blue-700 dark:text-blue-300">
                      Skor: {currentBenchmark.score} | Sıralama:{' '}
                      {currentBenchmark.rank} | Yuzdelik:{' '}
                      {formatPercent(currentBenchmark.percentile)}
                    </p>
                  </div>
                  <span className="text-2xl font-bold text-blue-900 dark:text-blue-200">
                    #{currentBenchmark.rank}
                  </span>
                </div>
              </div>
            )}

            {/* All reps ranking */}
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {benchmarks.map((bm) => {
                const isCurrentRep = bm.user_id === userId;
                return (
                  <div
                    key={bm.user_id}
                    className={`flex items-center justify-between px-2 py-2 ${isCurrentRep ? 'rounded bg-blue-50 font-semibold dark:bg-blue-900/10' : ''}`}
                  >
                    <div className="flex items-center gap-3">
                      <span className="w-8 text-center text-sm text-gray-500 dark:text-gray-400">
                        {bm.rank}
                      </span>
                      <span className="text-sm text-gray-900 dark:text-white">
                        {bm.user_name}
                      </span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-sm text-gray-700 dark:text-gray-300">
                        {bm.score}
                      </span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        {formatPercent(bm.percentile)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
