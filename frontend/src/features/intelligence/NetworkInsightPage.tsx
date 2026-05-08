import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { TrendingUp, TrendingDown, Minus } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { networkIntelligenceApi } from '../../lib/api';

/**
 * S-F — network intelligence page (manager view).
 *
 * Composes the existing benchmark services into a single
 * "tenant vs. segment" insight rollup.
 */

const VERDICT_BADGE: Record<
  string,
  { variant: 'success' | 'info' | 'warning' | 'danger'; label: string; icon: React.ReactNode }
> = {
  leading: { variant: 'success', label: 'Önde', icon: <TrendingUp className="h-3 w-3" /> },
  on_par: { variant: 'info', label: 'Eşit', icon: <Minus className="h-3 w-3" /> },
  lagging: { variant: 'warning', label: 'Geride', icon: <TrendingDown className="h-3 w-3" /> },
  critical: { variant: 'danger', label: 'Kritik', icon: <TrendingDown className="h-3 w-3" /> },
  unknown: { variant: 'info', label: 'Veri yok', icon: <Minus className="h-3 w-3" /> },
};

export default function NetworkInsightPage() {
  const [segmentKey, setSegmentKey] = useState<string | undefined>(undefined);

  const segmentsQuery = useQuery({
    queryKey: ['network-intelligence', 'segments'],
    queryFn: () => networkIntelligenceApi.segments(),
  });

  const overviewQuery = useQuery({
    queryKey: ['network-intelligence', 'overview', segmentKey ?? 'default'],
    queryFn: () => networkIntelligenceApi.overview(segmentKey),
  });

  const segments = segmentsQuery.data?.items ?? [];
  const overview = overviewQuery.data;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Network Intelligence"
        description="Senin tenant'ın segment medyanına göre nasıl performans gösteriyor"
      />

      {segments.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-caption text-slate-500">Segment:</span>
          {segments.slice(0, 8).map((seg) => (
            <button
              key={seg.segment_key}
              onClick={() => setSegmentKey(seg.segment_key)}
              className={`rounded-full px-3 py-1 text-caption transition ${
                segmentKey === seg.segment_key
                  ? 'bg-honeywell-red text-white'
                  : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
              }`}
            >
              {seg.name}
            </button>
          ))}
        </div>
      )}

      {overviewQuery.isLoading && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      )}

      {!overviewQuery.isLoading && overview && overview.metrics.length === 0 && (
        <EmptyState
          title="Henüz benchmark verisi yok"
          description="Nightly batch yeterli veri toplayınca burada görünecek."
        />
      )}

      {!overviewQuery.isLoading && overview && overview.metrics.length > 0 && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {overview.metrics.map((m) => {
            const verdict = VERDICT_BADGE[m.verdict] ?? VERDICT_BADGE.unknown;
            return (
              <Card key={m.key}>
                <div className="flex items-center justify-between">
                  <span className="text-caption text-slate-500">{m.label}</span>
                  <Badge variant={verdict.variant}>
                    <span className="inline-flex items-center gap-1">
                      {verdict.icon}
                      {verdict.label}
                    </span>
                  </Badge>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <div>
                    <div className="text-caption text-slate-500">Bizim</div>
                    <div className="text-heading-3 tabular-nums">
                      {m.tenant_value !== null ? m.tenant_value.toFixed(2) : '—'}
                    </div>
                  </div>
                  <div>
                    <div className="text-caption text-slate-500">Segment</div>
                    <div className="text-heading-3 tabular-nums text-slate-500">
                      {m.segment_value !== null ? m.segment_value.toFixed(2) : '—'}
                    </div>
                  </div>
                </div>
                {m.gap_pct !== null && (
                  <div className="mt-2 text-caption text-slate-500">
                    Fark:{' '}
                    <span
                      className={`tabular-nums ${
                        m.gap_pct >= 0 ? 'text-success' : 'text-warning'
                      }`}
                    >
                      {m.gap_pct >= 0 ? '+' : ''}
                      {m.gap_pct.toFixed(1)}%
                    </span>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {overview && overview.snapshot_date && (
        <p className="text-caption text-slate-400">
          Son güncelleme: {overview.snapshot_date}
          {overview.sample_size != null && ` · n=${overview.sample_size}`}
        </p>
      )}
    </div>
  );
}
