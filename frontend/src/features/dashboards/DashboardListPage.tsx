import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  Plus,
  LayoutGrid,
  Trash2,
  Star,
  ArrowRight,
  Lock,
  Globe,
  User,
  Pencil,
} from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { dashboardsApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import type { DashboardConfig } from '../../lib/types';

/**
 * Parse the widgets_json blob to count how many widgets the dashboard
 * holds. Used to render a meaningful preview thumbnail instead of an
 * empty card. Failures degrade gracefully to 0.
 */
function parseWidgetCount(widgetsJson: string | undefined | null): number {
  if (!widgetsJson) return 0;
  try {
    const parsed = JSON.parse(widgetsJson);
    return Array.isArray(parsed) ? parsed.length : 0;
  } catch {
    return 0;
  }
}

interface ExecutedWidget {
  widget_id?: string;
  title?: string;
  type?: string;
  // Values arrive in different shapes depending on widget type — KPIs
  // surface a single number, charts return arrays. We just need the
  // first numeric scalar we can find for the preview tile.
  value?: number | string;
  data?: unknown;
  total?: number;
  count?: number;
}

interface ExecuteResponse {
  data?: { widgets?: ExecutedWidget[] };
  widgets?: ExecutedWidget[];
}

/**
 * Try to pull a "headline number" out of an executed-widget payload.
 * Different widget types serialise their data differently (KPI,
 * counter, bar chart, table…) so we walk a small set of common
 * shapes; anything we can't reduce to a primitive is rendered as
 * "—" and the user can click into the dashboard for the full view.
 */
function extractHeadline(widget: ExecutedWidget): string {
  const candidates: unknown[] = [
    widget.value,
    widget.total,
    widget.count,
    typeof widget.data === 'number' ? widget.data : undefined,
  ];
  if (Array.isArray(widget.data)) {
    candidates.push(widget.data.length);
  } else if (widget.data && typeof widget.data === 'object') {
    const obj = widget.data as Record<string, unknown>;
    candidates.push(obj.value, obj.total, obj.count);
  }
  for (const c of candidates) {
    if (typeof c === 'number' && Number.isFinite(c)) {
      return c >= 1000 ? `${(c / 1000).toFixed(1)}k` : String(c);
    }
    if (typeof c === 'string' && c.length > 0) {
      return c;
    }
  }
  return '—';
}

/**
 * LivePreviewTiles — runs the dashboard's `execute` endpoint and
 * renders up to 4 KPI tiles using real values. Replaces the earlier
 * synthetic 4-cell skeleton that just showed how many widgets were
 * configured. Errors fall back to the skeleton tiles so a flaky
 * widget can't take the whole list page down.
 */
function LivePreviewTiles({
  dashboardId,
  widgetCount,
}: {
  dashboardId: number;
  widgetCount: number;
}) {
  const { data, isLoading, isError } = useQuery<ExecuteResponse>({
    queryKey: ['dashboard-execute', dashboardId],
    queryFn: () => dashboardsApi.execute(dashboardId),
    // Each card runs the dashboard, so cache aggressively to avoid
    // refetching on every list render. A user opening + closing the
    // detail page will still get fresh data via that page's own
    // execute call.
    staleTime: 60_000,
    refetchOnWindowFocus: false,
    enabled: widgetCount > 0,
  });

  const widgets = (data?.data?.widgets ?? data?.widgets ?? []).slice(0, 4);
  const skeletonCells = Array.from({ length: 4 }, (_, i) => i < Math.min(widgetCount, 4));

  if (widgetCount === 0 || isError || (!isLoading && widgets.length === 0)) {
    // Fall back to the original "filled square" preview when there
    // is nothing executable yet (empty dashboard, save before run,
    // or transient backend error).
    return (
      <div className="grid grid-cols-2 gap-1 rounded-xl border border-slate-200 bg-linear-to-br from-slate-50 to-white p-2 dark:border-slate-800 dark:from-slate-900 dark:to-slate-900/40">
        {skeletonCells.map((filled, i) => (
          <div
            key={i}
            className={[
              'h-10 rounded-md',
              filled
                ? 'bg-honeywell-red/10 ring-1 ring-inset ring-honeywell-red/15'
                : 'bg-slate-100 ring-1 ring-inset ring-slate-200/60 dark:bg-slate-800/40 dark:ring-slate-700/60',
            ].join(' ')}
          />
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 gap-1.5 rounded-xl border border-slate-200 bg-linear-to-br from-slate-50 to-white p-2 dark:border-slate-800 dark:from-slate-900 dark:to-slate-900/40">
      {Array.from({ length: 4 }, (_, i) => {
        const w = widgets[i];
        if (isLoading) {
          return (
            <div
              key={i}
              className="h-12 animate-pulse rounded-md bg-slate-100 ring-1 ring-inset ring-slate-200/60 dark:bg-slate-800/60 dark:ring-slate-700/60"
            />
          );
        }
        if (!w) {
          return (
            <div
              key={i}
              className="h-12 rounded-md bg-slate-100 ring-1 ring-inset ring-slate-200/60 dark:bg-slate-800/40 dark:ring-slate-700/60"
            />
          );
        }
        return (
          <div
            key={i}
            className="flex h-12 flex-col justify-center overflow-hidden rounded-md bg-honeywell-red/5 px-2 ring-1 ring-inset ring-honeywell-red/15"
          >
            <span className="truncate text-[10px] uppercase tracking-wider text-honeywell-red/80">
              {w.title ?? w.type ?? `Widget ${i + 1}`}
            </span>
            <span className="truncate text-[14px] font-semibold tabular-nums text-honeywell-red">
              {extractHeadline(w)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function DashboardListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState({ name: '', widgets_json: '[]', is_default: false });

  // Round-13 R13-API-1 — list endpoint emits canonical `items` plus
  // legacy `data` alias; prefer items so the alias can be retired.
  const { data, isLoading } = useQuery<{
    items?: DashboardConfig[];
    data?: DashboardConfig[];
  }>({
    queryKey: ['dashboards'],
    queryFn: () => dashboardsApi.list(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => dashboardsApi.create(payload),
    onSuccess: (result: { data: DashboardConfig }) => {
      toast.success('Pano oluşturuldu');
      setModalOpen(false);
      setForm({ name: '', widgets_json: '[]', is_default: false });
      queryClient.invalidateQueries({ queryKey: ['dashboards'] });
      // New dashboards land on the editor — they have no widgets yet.
      navigate(`/dashboards/${result.data.id}/edit`);
    },
    onError: () => toast.error('Pano oluşturulamadı'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => dashboardsApi.remove(id),
    onSuccess: () => {
      toast.success('Pano silindi');
      queryClient.invalidateQueries({ queryKey: ['dashboards'] });
    },
    onError: () => toast.error('Pano silinemedi'),
  });

  const dashboards = data?.items ?? data?.data ?? [];

  return (
    <div>
      <PageHeader title="Panolar" description="Özel rapor panoları oluşturun ve yönetin">
        {dashboards.length > 0 && (
          <Button onClick={() => setModalOpen(true)}>
            <Plus size={14} />
            Yeni Pano
          </Button>
        )}
      </PageHeader>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-[220px] rounded-2xl" />
          ))}
        </div>
      ) : dashboards.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white py-2 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <EmptyState
            variant="default"
            icon={<LayoutGrid size={20} />}
            title="Henüz pano yok"
            description="Raporlarınızı bir araya getirmek için pano oluşturun"
            action={
              <Button onClick={() => setModalOpen(true)} variant="secondary">
                <Plus size={14} />
                Pano Oluştur
              </Button>
            }
          />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {dashboards.map((d) => {
            const widgetCount = parseWidgetCount(d.widgets_json);
            // Visibility heuristic — DashboardConfig carries a free-form
            // `visibility` string when set; default to "private". Used
            // only to drive the icon + label in the meta row.
            const visibility =
              (d as { visibility?: string }).visibility ??
              ((d as { is_public?: boolean }).is_public ? 'public' : 'private');
            const VisIcon = visibility === 'public' ? Globe : visibility === 'team' ? User : Lock;
            const visLabel =
              visibility === 'public' ? 'Herkese açık' : visibility === 'team' ? 'Ekip' : 'Özel';
            return (
              <div
                key={d.id}
                className="group flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) transition-all hover:-translate-y-px hover:border-honeywell-red/30 hover:shadow-(--shadow-sm) dark:border-slate-800 dark:bg-slate-900"
              >
                <button
                  type="button"
                  onClick={() => navigate(`/dashboards/${d.id}`)}
                  className="flex flex-1 flex-col gap-4 p-5 text-left"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 items-start gap-2.5">
                      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                        <LayoutGrid size={14} />
                      </span>
                      <div className="min-w-0">
                        <h3 className="truncate text-[14px] font-semibold text-slate-900 dark:text-white">
                          {d.name}
                        </h3>
                        <p className="mt-0.5 text-[11px] tabular-nums text-slate-400 dark:text-slate-500">
                          {widgetCount} widget
                        </p>
                      </div>
                    </div>
                    {d.is_default && (
                      <Badge variant="warning" size="sm">
                        <Star size={10} fill="currentColor" />
                        Varsayılan
                      </Badge>
                    )}
                  </div>

                  <LivePreviewTiles dashboardId={d.id} widgetCount={widgetCount} />

                  <dl className="grid grid-cols-2 gap-3 text-[12px]">
                    <div>
                      <dt className="text-overline text-slate-400 dark:text-slate-500">Sahip</dt>
                      <dd className="mt-0.5 truncate text-slate-700 dark:text-slate-200">
                        {(d as { owner_name?: string }).owner_name ?? 'Sen'}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-overline text-slate-400 dark:text-slate-500">
                        Görünürlük
                      </dt>
                      <dd className="mt-0.5 flex items-center gap-1 text-slate-700 dark:text-slate-200">
                        <VisIcon size={11} className="text-slate-400" />
                        {visLabel}
                      </dd>
                    </div>
                    <div className="col-span-2">
                      <dt className="text-overline text-slate-400 dark:text-slate-500">
                        Son Güncelleme
                      </dt>
                      <dd className="mt-0.5 text-slate-700 tabular-nums dark:text-slate-200">
                        {d.updated_at
                          ? formatDateTime(d.updated_at)
                          : d.created_at
                            ? formatDateTime(d.created_at)
                            : '—'}
                      </dd>
                    </div>
                  </dl>
                </button>

                <div className="flex items-center justify-between gap-2 border-t border-slate-100 bg-slate-50/50 px-4 py-2.5 dark:border-slate-800 dark:bg-slate-900/40">
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        if (confirm('Bu panoyu silmek istediğinize emin misiniz?')) {
                          deleteMutation.mutate(d.id);
                        }
                      }}
                      aria-label="Sil"
                      title="Sil"
                    >
                      <Trash2 size={13} className="text-red-500" />
                    </Button>
                    {/* Round-9 — pencil routes to editor; the rest of the
                        card is the run/view experience. */}
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => navigate(`/dashboards/${d.id}/edit`)}
                      aria-label="Düzenle"
                      title="Düzenle"
                    >
                      <Pencil size={13} className="text-slate-500" />
                    </Button>
                  </div>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={() => navigate(`/dashboards/${d.id}`)}
                  >
                    Panoyu Aç
                    <ArrowRight size={13} />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Yeni Pano"
        size="md"
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              İptal
            </Button>
            <Button type="submit" form="dashboard-create-form" loading={createMutation.isPending}>
              Oluştur
            </Button>
          </>
        }
      >
        <form
          id="dashboard-create-form"
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate({
              name: form.name,
              widgets_json: form.widgets_json,
              is_default: form.is_default,
            });
          }}
          className="space-y-4"
        >
          <Input
            label="Pano Adı"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />
          <label className="flex cursor-pointer select-none items-center gap-2.5 rounded-[10px] border border-slate-200 bg-slate-50/60 px-3.5 py-2.5 text-[13px] text-slate-700 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
            <input
              type="checkbox"
              checked={form.is_default}
              onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
              className="h-4 w-4 cursor-pointer rounded-[4px] border-slate-300 text-honeywell-red focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800"
            />
            Varsayılan pano olarak ayarla
          </label>
        </form>
      </Modal>
    </div>
  );
}
