import type { ReactNode } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  Calendar as CalendarIcon,
  FileSignature,
  CheckCircle2,
  AlertTriangle,
  RefreshCcw,
  Plug,
  Activity,
} from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { integrationsApi } from '../../lib/api';
import { onIntegrationChanged } from '../../lib/cacheInvalidation';

import type { CalendarHealth, CalendarStatus, EsignStatus } from '../../lib/types';

/* ─────────────────────── IntegrationCard ─────────────────────── */

type ConnectionTone = 'connected' | 'warning' | 'disconnected';

interface ConnectionStatus {
  tone: ConnectionTone;
  label: string;
}

/**
 * Compute the visible status from the underlying connected/token flags.
 *
 * - `connected: true` + `token_present: true`  → connected
 * - `connected: true` + `token_present: false` → warning (re-auth needed)
 * - `connected: false`                          → disconnected
 *
 * The warning case is the important one — historically the page surfaced
 * "Bağlı + token yok" simultaneously, which is internally contradictory.
 * We collapse that into a single "Token süresi doldu" warning state.
 */
function computeStatus(connected: boolean, tokenPresent: boolean | undefined): ConnectionStatus {
  if (!connected) return { tone: 'disconnected', label: 'Bağlı Değil' };
  if (tokenPresent === false) return { tone: 'warning', label: 'Token süresi doldu' };
  return { tone: 'connected', label: 'Bağlı' };
}

const TONE_TO_BADGE: Record<ConnectionTone, 'success' | 'warning' | 'default'> = {
  connected: 'success',
  warning: 'warning',
  disconnected: 'default',
};

const TONE_TO_MEDALLION: Record<ConnectionTone, string> = {
  connected:
    'bg-emerald-50 text-emerald-700 ring-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-400 dark:ring-emerald-900/40',
  warning:
    'bg-amber-50 text-amber-700 ring-amber-100 dark:bg-amber-950/30 dark:text-amber-400 dark:ring-amber-900/40',
  disconnected:
    'bg-slate-50 text-slate-500 ring-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700',
};

interface IntegrationCardProps {
  /** Provider logo / icon */
  icon: ReactNode;
  /** Title (e.g. "Google Takvim"). */
  title: string;
  /** Provider tagline shown under the title. */
  subtitle: string;
  /** Skeleton state. */
  loading?: boolean;
  /** Resolved connection status. */
  status: ConnectionStatus;
  /** Health row (only shown when connected). */
  health?: { label: string; ok: boolean | null } | null;
  /** Last-sync timestamp string. */
  lastSync?: string | null;
  /** Connected account / provider readout. */
  account?: string | null;
  /** Primary CTA — typically "Bağlan" or "Senkronize Et" or "Bağlantıyı Yenile". */
  primaryAction: {
    label: string;
    onClick: () => void;
    loading?: boolean;
    variant?: 'primary' | 'secondary';
  };
  /** Optional secondary action (e.g. health re-check). */
  secondaryAction?: { label: string; onClick: () => void; loading?: boolean; icon?: ReactNode };
}

/**
 * IntegrationCard — single source of truth for an integration block.
 *
 * Layout:
 *   - Header: provider medallion + name + subtitle, status Badge anchored right
 *   - Body: two-column metadata grid (Account / Last sync / Health)
 *   - Footer: action row pinned to a slate-tinted strip
 */
function IntegrationCard({
  icon,
  title,
  subtitle,
  loading,
  status,
  health,
  lastSync,
  account,
  primaryAction,
  secondaryAction,
}: IntegrationCardProps) {
  const isWarning = status.tone === 'warning';

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-start justify-between gap-4 px-5 py-4">
        <div className="flex min-w-0 items-start gap-3">
          <span
            className={[
              'inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-[12px] ring-1 ring-inset',
              TONE_TO_MEDALLION[status.tone],
            ].join(' ')}
          >
            {icon}
          </span>
          <div className="min-w-0">
            <h3 className="text-[14px] font-semibold text-slate-900 dark:text-white">{title}</h3>
            <p className="mt-0.5 text-[12px] text-slate-500 dark:text-slate-400">{subtitle}</p>
          </div>
        </div>
        <Badge variant={TONE_TO_BADGE[status.tone]} size="md" dot>
          {status.label}
        </Badge>
      </div>

      {loading ? (
        <div className="px-5 pb-5">
          <Skeleton variant="line" count={3} />
        </div>
      ) : (
        <>
          <dl className="grid grid-cols-1 gap-3 border-t border-slate-100 px-5 py-4 sm:grid-cols-2 dark:border-slate-800">
            <div>
              <dt className="text-overline text-slate-400 dark:text-slate-500">Bağlı Hesap</dt>
              <dd className="mt-1 truncate text-[13px] text-slate-800 dark:text-slate-200">
                {account || '—'}
              </dd>
            </div>
            <div>
              <dt className="text-overline text-slate-400 dark:text-slate-500">
                Son Senkronizasyon
              </dt>
              <dd className="mt-1 truncate text-[13px] tabular-nums text-slate-800 dark:text-slate-200">
                {lastSync || '—'}
              </dd>
            </div>
            {health && (
              <div className="sm:col-span-2">
                <dt className="text-overline text-slate-400 dark:text-slate-500">Sağlık Durumu</dt>
                <dd className="mt-1 flex items-center gap-1.5 text-[13px]">
                  {health.ok === null ? (
                    <span className="text-slate-500 dark:text-slate-400">{health.label}</span>
                  ) : health.ok ? (
                    <>
                      <CheckCircle2 size={13} className="text-emerald-500" />
                      <span className="font-medium text-emerald-700 dark:text-emerald-400">
                        {health.label}
                      </span>
                    </>
                  ) : (
                    <>
                      <AlertTriangle size={13} className="text-amber-500" />
                      <span className="font-medium text-amber-700 dark:text-amber-400">
                        {health.label}
                      </span>
                    </>
                  )}
                </dd>
              </div>
            )}
          </dl>

          {/* Warning-state advisory: surfaces the "token expired" copy so the
              user understands why "Bağlantıyı Yenile" is the right next step. */}
          {isWarning && (
            <div className="mx-5 mb-4 flex items-start gap-2.5 rounded-xl border border-amber-100 bg-amber-50/60 p-3 dark:border-amber-900/40 dark:bg-amber-950/20">
              <AlertTriangle
                size={14}
                className="mt-0.5 shrink-0 text-amber-600 dark:text-amber-400"
              />
              <p className="text-[12px] leading-5 text-amber-900 dark:text-amber-200">
                Token süresi doldu. Senkronizasyonu sürdürmek için bağlantıyı yenileyin.
              </p>
            </div>
          )}
        </>
      )}

      <div className="flex items-center justify-end gap-2 border-t border-slate-100 bg-slate-50/50 px-4 py-2.5 dark:border-slate-800 dark:bg-slate-900/40">
        {secondaryAction && (
          <Button
            variant="tertiary"
            size="sm"
            onClick={secondaryAction.onClick}
            loading={secondaryAction.loading}
          >
            {secondaryAction.icon}
            {secondaryAction.label}
          </Button>
        )}
        <Button
          variant={primaryAction.variant ?? 'primary'}
          size="sm"
          onClick={primaryAction.onClick}
          loading={primaryAction.loading}
        >
          <Plug size={13} />
          {primaryAction.label}
        </Button>
      </div>
    </div>
  );
}

/* ─────────────────────── Page ─────────────────────── */

export default function IntegrationsPage() {
  const queryClient = useQueryClient();

  const calendarQuery = useQuery<CalendarStatus>({
    queryKey: ['integrations', 'calendar'],
    queryFn: () => integrationsApi.getCalendarStatus(),
  });

  const calendarHealthQuery = useQuery<CalendarHealth>({
    queryKey: ['integrations', 'calendar', 'health'],
    queryFn: () => integrationsApi.getCalendarHealth(),
  });

  const esignQuery = useQuery<EsignStatus>({
    queryKey: ['integrations', 'esign'],
    queryFn: () => integrationsApi.getEsignStatus(),
  });

  const connectCalendarMutation = useMutation({
    mutationFn: () => integrationsApi.connectCalendar({ provider: 'google' }),
    onSuccess: () => {
      toast.success('Takvim başarıyla bağlandı');
      onIntegrationChanged(queryClient, 'calendar');
    },
    onError: () => toast.error('Takvim bağlanamadı'),
  });

  const syncCalendarMutation = useMutation({
    mutationFn: () => integrationsApi.syncCalendar(),
    onSuccess: () => toast.success('Takvim senkronize edildi'),
    onError: () => toast.error('Senkronizasyon başarısız'),
  });

  const connectEsignMutation = useMutation({
    mutationFn: () => integrationsApi.connectEsign({ provider: 'docusign' }),
    onSuccess: () => {
      toast.success('E-imza başarıyla bağlandı');
      onIntegrationChanged(queryClient, 'esign');
    },
    onError: () => toast.error('E-imza bağlanamadı'),
  });

  const calendar = calendarQuery.data;
  const calendarHealth = calendarHealthQuery.data;
  const esign = esignQuery.data;

  const calendarStatus = computeStatus(calendar?.connected ?? false, calendar?.token_present);
  const esignStatus = computeStatus(esign?.connected ?? false, undefined);

  const calendarPrimary = (() => {
    if (calendarStatus.tone === 'warning') {
      return {
        label: 'Bağlantıyı Yenile',
        onClick: () => connectCalendarMutation.mutate(),
        loading: connectCalendarMutation.isPending,
      };
    }
    if (calendarStatus.tone === 'connected') {
      return {
        label: 'Senkronize Et',
        onClick: () => syncCalendarMutation.mutate(),
        loading: syncCalendarMutation.isPending,
        variant: 'secondary' as const,
      };
    }
    return {
      label: 'Bağlan',
      onClick: () => connectCalendarMutation.mutate(),
      loading: connectCalendarMutation.isPending,
    };
  })();

  const calendarHealthRow = calendarHealthQuery.isLoading
    ? { label: 'Kontrol ediliyor...', ok: null as null }
    : calendarHealth
      ? {
          // When `ok === false`, surface the precise error from the
          // backend (audit F-22) so the user gets actionable detail
          // instead of the generic "unknown" fallback.
          label: calendarHealth.ok
            ? 'OK'
            : calendarHealth.error || calendarHealth.status || 'unknown',
          ok: calendarHealth.ok,
        }
      : null;

  return (
    <div>
      <PageHeader
        title="Entegrasyonlar"
        description="Harici servis entegrasyonlarınızı yönetin ve sağlık durumunu takip edin"
      />

      {(calendarQuery.isError || esignQuery.isError) && (
        <div className="mb-4">
          <QueryErrorBanner
            variant="block"
            onRetry={() => {
              if (calendarQuery.isError) calendarQuery.refetch();
              if (esignQuery.isError) esignQuery.refetch();
            }}
          />
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <IntegrationCard
          icon={<CalendarIcon size={20} />}
          title="Takvim Entegrasyonu"
          subtitle="Google / Microsoft 365 takvimleri"
          loading={calendarQuery.isLoading}
          status={calendarStatus}
          health={calendarHealthRow}
          lastSync={calendar?.last_sync_at ?? null}
          account={calendar?.provider ?? null}
          primaryAction={calendarPrimary}
          secondaryAction={
            calendarStatus.tone === 'connected'
              ? {
                  label: 'Sağlığı Yeniden Kontrol Et',
                  onClick: () => calendarHealthQuery.refetch(),
                  loading: calendarHealthQuery.isFetching,
                  icon: <Activity size={13} />,
                }
              : undefined
          }
        />

        <IntegrationCard
          icon={<FileSignature size={20} />}
          title="E-İmza Entegrasyonu"
          subtitle="DocuSign / Adobe Sign"
          loading={esignQuery.isLoading}
          status={esignStatus}
          lastSync={null}
          account={esign?.provider ?? null}
          primaryAction={{
            label: esignStatus.tone === 'connected' ? 'Yenile' : 'Bağlan',
            onClick: () => connectEsignMutation.mutate(),
            loading: connectEsignMutation.isPending,
            variant: esignStatus.tone === 'connected' ? 'secondary' : 'primary',
          }}
          secondaryAction={
            esignStatus.tone === 'connected'
              ? {
                  label: 'Yeniden Kontrol Et',
                  onClick: () => esignQuery.refetch(),
                  loading: esignQuery.isFetching,
                  icon: <RefreshCcw size={13} />,
                }
              : undefined
          }
        />
      </div>
    </div>
  );
}
