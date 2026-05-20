/**
 * SystemHealthPage
 *
 * Live operational view of the backend's `/api/health` endpoint.
 * Surfaces the same payload the load balancer uses to decide whether
 * the container is healthy, but with friendly Turkish labels and
 * colour coding so admins can troubleshoot at a glance.
 *
 * Audit finding #5.7: the backend returns rich circuit-breaker /
 * dependency / event-bus state, but no admin page consumes it. Reps
 * have to ping engineering to know if Claude / Qdrant / the embedding
 * model are healthy. This page closes that loop.
 *
 * The page polls every 30 seconds while open. We rely on
 * tanstack-query's window-focus refetch to give an instant refresh
 * when the operator switches back to the tab.
 */

import { useQuery } from '@tanstack/react-query';
import { Activity, RotateCw, ShieldAlert, ShieldCheck } from 'lucide-react';
import axios from 'axios';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { useFeatureFlags } from '../../contexts/FeatureFlagContext';

interface HealthPayload {
  status: 'healthy' | 'degraded' | 'unhealthy' | string;
  checks: Record<string, string>;
  circuits: Record<
    string,
    { state: 'closed' | 'open' | 'half_open' | string; failure_count: number }
  >;
  version: string;
  uptime_seconds: number;
}

// The health endpoint sits at /api/health (no /v1 prefix), so we
// can't reuse the configured ``api`` axios instance — that one
// targets /api/v1/. Build a one-off axios call against the same
// origin instead.
const HEALTH_URL = '/api/health';

async function fetchHealth(): Promise<HealthPayload> {
  const { data } = await axios.get<HealthPayload>(HEALTH_URL, {
    withCredentials: true,
    timeout: 5_000,
  });
  return data;
}

function uptimeLabel(seconds: number): string {
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days}g ${hours}sa`;
  if (hours > 0) return `${hours}sa ${minutes}dk`;
  return `${minutes}dk`;
}

const CHECK_LABELS: Record<string, string> = {
  database: 'Veritabanı',
  qdrant: 'Vektör DB (Qdrant)',
  embedding_model: 'Gömme Modeli',
  event_bus: 'Olay Veriyolu',
};

const CIRCUIT_LABELS: Record<string, string> = {
  claude_api: 'Claude API',
  graph_api: 'Microsoft Graph',
  currency_api: 'Döviz Kuru API',
  qdrant: 'Qdrant',
};

export default function SystemHealthPage() {
  const { release, env } = useFeatureFlags();
  // R14-FE-1 exempt: page already renders a custom isError card with a
  // Sağlık endpoint'i yanıt vermedi message inline. Wrapping in QueryErrorBanner
  // would double up the failure UX.
  const { data, isLoading, isError, refetch, isFetching } = useQuery<HealthPayload>({
    queryKey: ['system-health'],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
    staleTime: 0,
    retry: 0,
  });

  const overallTone =
    data?.status === 'healthy' ? 'success' : data?.status === 'degraded' ? 'warning' : 'danger';

  return (
    <div>
      <PageHeader
        title="Sistem Sağlığı"
        description="Backend bağımlılıkları, devre kesiciler ve uptime"
      >
        <Button variant="secondary" onClick={() => refetch()} loading={isFetching}>
          <RotateCw size={14} />
          Yenile
        </Button>
      </PageHeader>

      {isLoading ? (
        <Skeleton variant="card" count={3} />
      ) : isError || !data ? (
        <Card>
          <div className="flex items-center gap-2 p-4 text-rose-600">
            <ShieldAlert size={16} />
            Sağlık endpoint'i yanıt vermedi — backend container'ı yeniden başlıyor olabilir.
          </div>
        </Card>
      ) : (
        <div className="space-y-4">
          {/* Headline status */}
          <Card>
            <div className="flex flex-wrap items-center gap-4 p-4">
              <span className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-honeywell-red/10 text-honeywell-red">
                {data.status === 'healthy' ? <ShieldCheck size={20} /> : <ShieldAlert size={20} />}
              </span>
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="text-[16px] font-semibold text-slate-900 dark:text-white">
                    Genel Durum
                  </h3>
                  <Badge variant={overallTone} size="sm">
                    {data.status === 'healthy'
                      ? 'Sağlıklı'
                      : data.status === 'degraded'
                        ? 'Sınırlı'
                        : 'Sağlıksız'}
                  </Badge>
                </div>
                <p className="mt-0.5 text-[12px] text-slate-500">
                  Sürüm <span className="font-mono">{data.version}</span> · {env} · uptime{' '}
                  <span className="tabular-nums">{uptimeLabel(data.uptime_seconds)}</span>
                  {release !== 'unknown' && (
                    <>
                      {' '}
                      · build <span className="font-mono">{release.slice(0, 8)}</span>
                    </>
                  )}
                </p>
              </div>
            </div>
          </Card>

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* Dependency checks */}
            <Card title="Bağımlılıklar">
              <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                {Object.entries(data.checks).map(([key, status]) => {
                  const label = CHECK_LABELS[key] ?? key;
                  const ok = status === 'ok' || status === 'loaded' || status.endsWith('handlers');
                  return (
                    <li
                      key={key}
                      className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0"
                    >
                      <span className="text-[13px] text-slate-700 dark:text-slate-300">
                        {label}
                      </span>
                      <Badge variant={ok ? 'success' : 'danger'} size="sm">
                        {status}
                      </Badge>
                    </li>
                  );
                })}
              </ul>
            </Card>

            {/* Circuit breakers */}
            <Card title="Devre Kesiciler">
              {Object.keys(data.circuits).length === 0 ? (
                <p className="text-[12px] text-slate-500">Devre kesici bilgisi yok.</p>
              ) : (
                <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                  {Object.entries(data.circuits).map(([key, breaker]) => {
                    const label = CIRCUIT_LABELS[key] ?? key;
                    const tone =
                      breaker.state === 'closed'
                        ? 'success'
                        : breaker.state === 'half_open'
                          ? 'warning'
                          : 'danger';
                    return (
                      <li
                        key={key}
                        className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0"
                      >
                        <div className="flex items-center gap-2">
                          <Activity size={12} className="text-slate-400" />
                          <span className="text-[13px] text-slate-700 dark:text-slate-300">
                            {label}
                          </span>
                        </div>
                        <div className="flex items-center gap-2">
                          {breaker.failure_count > 0 && (
                            <span className="text-[11px] tabular-nums text-rose-600">
                              {breaker.failure_count} hata
                            </span>
                          )}
                          <Badge variant={tone as 'success' | 'warning' | 'danger'} size="sm">
                            {breaker.state === 'closed'
                              ? 'kapalı'
                              : breaker.state === 'half_open'
                                ? 'yarı-açık'
                                : 'açık'}
                          </Badge>
                        </div>
                      </li>
                    );
                  })}
                </ul>
              )}
            </Card>
          </div>

          <p className="text-[11px] text-slate-400">
            Sayfa 30 saniyede bir otomatik yenilenir. Sentry'deki olay korelasyonu için yukarıda
            görünen build hash'ini destek talebine ekleyin.
          </p>
        </div>
      )}
    </div>
  );
}
