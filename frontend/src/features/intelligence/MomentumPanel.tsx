import { useQuery } from '@tanstack/react-query';
import { TrendingUp, TrendingDown, Minus, Activity } from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from 'recharts';

import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { momentumApi } from '../../lib/api';
import { formatDate } from '../../lib/formatters';

/**
 * Round-8 R8-DEAD-1 — surface the momentum service that was shipped in
 * v1.13 but never called from the frontend.
 *
 * Renders the latest momentum score + band + drivers, plus a 30-day
 * sparkline. Embed on OpportunityDetailPage.
 */
interface MomentumPanelProps {
  opportunityId: number;
}

const BAND_BADGE: Record<
  string,
  {
    variant: 'success' | 'info' | 'warning' | 'danger' | 'default';
    label: string;
    icon: React.ReactNode;
  }
> = {
  rising: { variant: 'success', label: 'Yükseliyor', icon: <TrendingUp className="h-3 w-3" /> },
  stable: { variant: 'info', label: 'Stabil', icon: <Minus className="h-3 w-3" /> },
  stalling: { variant: 'warning', label: 'Yavaşlıyor', icon: <Activity className="h-3 w-3" /> },
  declining: { variant: 'warning', label: 'Düşüyor', icon: <TrendingDown className="h-3 w-3" /> },
  dead: { variant: 'danger', label: 'Riskli', icon: <TrendingDown className="h-3 w-3" /> },
};

export function MomentumPanel({ opportunityId }: MomentumPanelProps) {
  const currentQuery = useQuery({
    queryKey: ['momentum', opportunityId],
    queryFn: () => momentumApi.getCurrent(opportunityId),
    enabled: opportunityId > 0,
  });

  const historyQuery = useQuery({
    queryKey: ['momentum', opportunityId, 'history', 30],
    queryFn: () => momentumApi.getHistory(opportunityId, 30),
    enabled: opportunityId > 0,
  });

  const current = currentQuery.data;
  const history = historyQuery.data?.items ?? [];

  if (currentQuery.isLoading) {
    return (
      <Card title="Momentum">
        <Skeleton className="h-32" />
      </Card>
    );
  }

  // Round-11 R11-FE-1 — surface error instead of silently rendering
  // the empty/'no data' state when the request actually failed.
  if (currentQuery.isError) {
    return (
      <Card title="Momentum" description="Veri yüklenemedi">
        <div className="rounded-[8px] border border-(--danger)/30 bg-(--danger-bg) p-3 text-[13px] text-(--danger)">
          {(currentQuery.error as Error | undefined)?.message ?? 'Momentum verisi yüklenemedi.'}
          <button
            type="button"
            className="ml-3 underline-offset-2 hover:underline"
            onClick={() => currentQuery.refetch()}
          >
            Tekrar dene
          </button>
        </div>
      </Card>
    );
  }

  if (!current || current.score === null) {
    return (
      <Card title="Momentum" description="Henüz momentum skoru hesaplanmadı">
        <EmptyState
          title="Veri yok"
          description="Nightly batch çalışınca skor görünecek."
          variant="compact"
          icon={<Activity className="h-8 w-8 text-slate-400" />}
        />
      </Card>
    );
  }

  // Round-10 R10-FE-13 — `stable` is always defined in BAND_BADGE; `!`
  // is the narrow form that lets the type drop the | undefined branch.
  const badge = BAND_BADGE[current.band] ?? BAND_BADGE.stable!;

  return (
    <Card
      title="Momentum"
      description={
        current.snapshot_date ? `${formatDate(current.snapshot_date)} itibarıyla` : undefined
      }
      action={
        <Badge variant={badge.variant}>
          <span className="inline-flex items-center gap-1">
            {badge.icon}
            {badge.label}
          </span>
        </Badge>
      }
    >
      <div className="flex items-baseline gap-3">
        <span className="text-heading-1 tabular-nums text-slate-900 dark:text-white">
          {current.score}
        </span>
        <span className="text-caption text-slate-500">/ 100</span>
      </div>

      {history.length > 1 && (
        <div className="mt-4 h-24">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={history}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" />
              <XAxis dataKey="snapshot_date" hide />
              <YAxis hide domain={[0, 100]} />
              <Tooltip
                formatter={(v) => [`${v}`, 'Skor']}
                labelFormatter={(label) => formatDate(String(label))}
              />
              <Line
                type="monotone"
                dataKey="score"
                stroke="var(--color-honeywell-red)"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {current.drivers.length > 0 && (
        <ul className="mt-4 space-y-1.5">
          {current.drivers.slice(0, 5).map((driver, idx) => (
            <li
              key={idx}
              className="flex items-center justify-between text-caption text-slate-600 dark:text-slate-400"
            >
              <span className="truncate">{driver.label}</span>
              <span
                className={`tabular-nums font-semibold ${
                  driver.impact > 0
                    ? 'text-success'
                    : driver.impact < 0
                      ? 'text-warning'
                      : 'text-slate-500'
                }`}
              >
                {driver.impact > 0 ? '+' : ''}
                {driver.impact}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default MomentumPanel;
