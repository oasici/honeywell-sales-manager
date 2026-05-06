/**
 * Self-contained intelligence panel for the opportunity detail page.
 *
 * Wires up four V5/V4 surfaces that the audit flagged as completely
 * unrendered despite being computed nightly on the backend:
 *
 *   1. Momentum drivers (V4 feature store) — explains the headline
 *      momentum_score with a per-driver breakdown.
 *   2. Similar deals (V5 deal_similarity_links) — nearest neighbours
 *      with similarity_score + reason.
 *   3. Objections (V5 objection_intelligence) — currently logged
 *      objections with severity + resolution status.
 *   4. Timing windows (V5 timing_engine) — recommended actions with
 *      urgency_score + window range.
 *
 * Each widget queries its own endpoint with React Query so a slow or
 * failing one never blocks the others. We deliberately render
 * compact, low-density cards so this panel can sit beneath the deal
 * info card without dwarfing it.
 */

import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { Activity, Sparkles, AlertCircle, Clock, ChevronDown, ChevronRight } from 'lucide-react';

import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { v5IntelligenceApi, featureStoreApi } from '../../lib/api';
import { formatCurrency, formatDateTime } from '../../lib/formatters';

interface Props {
  opportunityId: number;
}

// Cache aggressively — these endpoints are nightly-computed so
// hammering them on every detail-page mount is wasteful.
const STALE_TIME = 60_000;

function MomentumDriversWidget({ opportunityId }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['feature-store-latest', opportunityId],
    queryFn: () => featureStoreApi.getLatest(opportunityId),
    staleTime: STALE_TIME,
    refetchOnWindowFocus: false,
  });

  if (isLoading) return <Skeleton variant="card" />;
  if (!data) {
    return (
      <Card title="Momentum">
        <p className="text-[12px] text-slate-500">
          Henüz hesaplanmış bir feature snapshot yok — V4 nightly job sonrası gelecek.
        </p>
      </Card>
    );
  }

  const band = data.momentum_band ?? 'low';
  const bandTone =
    band === 'high' ? 'success' : band === 'medium' ? 'info' : 'warning';
  const bandLabel = band === 'high' ? 'Yüksek' : band === 'medium' ? 'Orta' : 'Düşük';

  return (
    <Card title="Momentum">
      <div className="flex items-baseline gap-3">
        <span className="text-3xl font-bold tabular-nums text-slate-900 dark:text-white">
          {data.momentum_score ?? '—'}
        </span>
        <Badge variant={bandTone as 'success' | 'info' | 'warning'} size="sm">
          {bandLabel}
        </Badge>
        {data.snapshot_date && (
          <span className="text-[11px] text-slate-400 tabular-nums">
            {data.snapshot_date}
          </span>
        )}
      </div>

      {data.momentum_drivers.length === 0 ? (
        <p className="mt-3 text-[12px] text-slate-500">
          Sürücü kaydı yok — momentum hesaplaması varsayılan ağırlıklarla ilerliyor.
        </p>
      ) : (
        <ul className="mt-3 space-y-1.5">
          {data.momentum_drivers.slice(0, 6).map((driver, i) => {
            const label = String(driver.label ?? `Sürücü ${i + 1}`);
            const contribution =
              typeof driver.contribution === 'number'
                ? driver.contribution
                : null;
            const positive =
              driver.direction === 'positive' ||
              (typeof contribution === 'number' && contribution > 0);
            return (
              <li
                key={i}
                className="flex items-center justify-between gap-2 text-[12px]"
              >
                <span className="truncate text-slate-700 dark:text-slate-300">
                  {label}
                </span>
                <span
                  className={`tabular-nums font-medium ${
                    positive
                      ? 'text-emerald-600 dark:text-emerald-400'
                      : 'text-rose-600 dark:text-rose-400'
                  }`}
                >
                  {contribution != null
                    ? `${positive && contribution > 0 ? '+' : ''}${contribution.toFixed(1)}`
                    : '—'}
                </span>
              </li>
            );
          })}
        </ul>
      )}

      {/* Surface a couple of trajectory dimensions we already
          deserialise — these used to live only in API JSON. */}
      <dl className="mt-4 grid grid-cols-2 gap-2 text-[11px]">
        <div>
          <dt className="text-overline text-slate-400">Aşama hızı</dt>
          <dd className="text-slate-700 tabular-nums dark:text-slate-200">
            {data.stage_velocity_days != null
              ? `${data.stage_velocity_days.toFixed(1)} gün`
              : '—'}
          </dd>
        </div>
        <div>
          <dt className="text-overline text-slate-400">Alıcı durumu</dt>
          <dd className="text-slate-700 dark:text-slate-200">
            {data.buyer_state ?? '—'}
          </dd>
        </div>
      </dl>
    </Card>
  );
}

function SimilarDealsWidget({ opportunityId }: Props) {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ['v5-similar', opportunityId],
    queryFn: () => v5IntelligenceApi.getSimilar(opportunityId, 5),
    staleTime: STALE_TIME,
    refetchOnWindowFocus: false,
  });

  if (isLoading) return <Skeleton variant="card" />;
  const items = data?.items ?? [];

  return (
    <Card title="Benzer Fırsatlar">
      {items.length === 0 ? (
        <p className="text-[12px] text-slate-500">
          Henüz benzerlik eşleşmesi yok — V5 nightly job daha fazla anlaşma birikince üretecek.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((sim) => (
            <li key={sim.related_opportunity_id}>
              <button
                type="button"
                onClick={() => navigate(`/opportunities/${sim.related_opportunity_id}`)}
                className="flex w-full items-center justify-between gap-3 rounded-md p-2 text-left hover:bg-slate-50 dark:hover:bg-slate-800/50"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium text-slate-900 dark:text-white">
                    {sim.related_title ?? `Fırsat #${sim.related_opportunity_id}`}
                  </p>
                  <p className="mt-0.5 truncate text-[11px] text-slate-500 dark:text-slate-400">
                    {sim.reason ?? sim.related_stage ?? ''}
                    {sim.related_amount != null && (
                      <>
                        {' · '}
                        {formatCurrency(sim.related_amount, 'TRY')}
                      </>
                    )}
                  </p>
                </div>
                <span className="shrink-0 rounded-md bg-honeywell-red/10 px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-honeywell-red">
                  %{Math.round((sim.similarity_score ?? 0) * 100)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function ObjectionsWidget({ opportunityId }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['v5-objections', opportunityId],
    queryFn: () => v5IntelligenceApi.getObjections(opportunityId),
    staleTime: STALE_TIME,
    refetchOnWindowFocus: false,
  });

  if (isLoading) return <Skeleton variant="card" />;
  const items = data?.items ?? [];
  const open = items.filter((o) => !o.resolved_flag);
  const resolved = items.filter((o) => o.resolved_flag);

  return (
    <Card title="İtirazlar">
      {items.length === 0 ? (
        <p className="text-[12px] text-slate-500">Bu fırsata ilişkin itiraz kaydı yok.</p>
      ) : (
        <>
          <div className="mb-2 flex items-center gap-3 text-[11px]">
            <span className="text-slate-500">
              <span className="font-semibold text-rose-600">{open.length}</span> açık
            </span>
            <span className="text-slate-500">
              <span className="font-semibold text-emerald-600">{resolved.length}</span>{' '}
              çözüldü
            </span>
          </div>
          <ul className="space-y-1.5">
            {items.slice(0, 5).map((o) => (
              <li
                key={o.id}
                className="flex items-start gap-2 rounded-md border border-slate-100 p-2 dark:border-slate-800"
              >
                <Badge
                  variant={
                    o.severity === 'high'
                      ? 'danger'
                      : o.severity === 'med'
                        ? 'warning'
                        : 'default'
                  }
                  size="sm"
                >
                  {o.objection_type}
                </Badge>
                {o.evidence_text && (
                  <span className="flex-1 truncate text-[12px] text-slate-600 dark:text-slate-300">
                    {o.evidence_text}
                  </span>
                )}
                {o.resolved_flag && (
                  <span className="shrink-0 text-[11px] text-emerald-600 dark:text-emerald-400">
                    çözüldü
                  </span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

function TimingWindowsWidget({ opportunityId }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['v5-timing-windows', opportunityId],
    queryFn: () => v5IntelligenceApi.getTimingWindows(opportunityId),
    staleTime: STALE_TIME,
    refetchOnWindowFocus: false,
  });

  if (isLoading) return <Skeleton variant="card" />;
  const items = data?.items ?? [];

  return (
    <Card title="Önerilen Aksiyon Pencereleri">
      {items.length === 0 ? (
        <p className="text-[12px] text-slate-500">
          Aktif öneri penceresi yok — sıradaki öneriler V5 timing engine tarafından
          tetikleniyor.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {items.slice(0, 4).map((w) => {
            const urgency = w.urgency_score ?? 0;
            const tone =
              urgency >= 0.75 ? 'danger' : urgency >= 0.5 ? 'warning' : 'info';
            return (
              <li
                key={w.id}
                className="rounded-md border border-slate-100 p-2 dark:border-slate-800"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[13px] font-medium text-slate-900 dark:text-white">
                    {w.action_type}
                  </span>
                  <Badge variant={tone as 'danger' | 'warning' | 'info'} size="sm">
                    %{Math.round(urgency * 100)}
                  </Badge>
                </div>
                <div className="mt-0.5 flex flex-wrap gap-2 text-[11px] text-slate-500">
                  {w.window_start && <span>{formatDateTime(w.window_start)} →</span>}
                  {w.window_end && <span>{formatDateTime(w.window_end)}</span>}
                </div>
                {w.reason_codes.length > 0 && (
                  <ul className="mt-1 flex flex-wrap gap-1">
                    {w.reason_codes.slice(0, 4).map((rc, i) => (
                      <li
                        key={i}
                        className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                      >
                        {/* R6-RENDER-9 — backend used to write a mixed
                            array (string + {ideal_hours, actual_hours,
                            segment_key} object), so older rows in prod
                            can still leak an object through the typed
                            string[] contract. Coerce defensively to
                            avoid React error #31. */}
                        {typeof rc === 'string'
                          ? rc
                          : Object.entries(rc as Record<string, unknown>)
                              .map(([k, v]) => `${k}=${String(v)}`)
                              .join(' · ')}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export default function OpportunityIntelligencePanel({ opportunityId }: Props) {
  // Collapsed by default so the detail page stays compact for users
  // who haven't asked for the deeper analytics. Persisted in
  // sessionStorage so flipping back and forth between deals doesn't
  // re-collapse on every navigation.
  const [open, setOpen] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false;
    return sessionStorage.getItem('opp-intel-panel-open') === '1';
  });

  function togglePanel() {
    const next = !open;
    setOpen(next);
    if (typeof window !== 'undefined') {
      sessionStorage.setItem('opp-intel-panel-open', next ? '1' : '0');
    }
  }

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={togglePanel}
        className="flex w-full items-center justify-between gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left shadow-(--shadow-xs) hover:border-honeywell-red/30 dark:border-slate-800 dark:bg-slate-900"
        aria-expanded={open}
      >
        <span className="flex items-center gap-2">
          <Sparkles size={16} className="text-honeywell-red" />
          <span className="text-[14px] font-semibold text-slate-900 dark:text-white">
            Akıllı İçgörüler
          </span>
          <span className="text-[11px] text-slate-500 dark:text-slate-400">
            momentum · benzerlik · itirazlar · zamanlama
          </span>
        </span>
        {open ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
      </button>

      {open && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div className="flex items-start gap-2">
            <Activity size={14} className="mt-1 shrink-0 text-slate-400" />
            <div className="flex-1">
              <MomentumDriversWidget opportunityId={opportunityId} />
            </div>
          </div>
          <div className="flex items-start gap-2">
            <Sparkles size={14} className="mt-1 shrink-0 text-slate-400" />
            <div className="flex-1">
              <SimilarDealsWidget opportunityId={opportunityId} />
            </div>
          </div>
          <div className="flex items-start gap-2">
            <AlertCircle size={14} className="mt-1 shrink-0 text-slate-400" />
            <div className="flex-1">
              <ObjectionsWidget opportunityId={opportunityId} />
            </div>
          </div>
          <div className="flex items-start gap-2">
            <Clock size={14} className="mt-1 shrink-0 text-slate-400" />
            <div className="flex-1">
              <TimingWindowsWidget opportunityId={opportunityId} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
