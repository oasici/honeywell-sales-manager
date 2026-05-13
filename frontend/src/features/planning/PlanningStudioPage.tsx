import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Trash2, LayoutGrid, UsersRound, ExternalLink } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { savedViewsApi } from '../../lib/api';
import { useT } from '../../hooks/useT';
import type { SavedView } from '../../lib/types';

function boardQuery(params: Record<string, string>) {
  return JSON.stringify(params);
}

export default function PlanningStudioPage() {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery<{
    items?: SavedView[];
    views?: SavedView[];
  }>({
    queryKey: ['saved-views'],
    queryFn: () => savedViewsApi.list(),
  });

  // Round-13 R13-API-1 — list endpoint now emits canonical `items`
  // plus the legacy `views` alias; prefer items so we can drop the
  // alias once all surfaces migrate.
  const views = data?.items ?? data?.views ?? [];

  const createMutation = useMutation({
    mutationFn: savedViewsApi.create,
    onSuccess: () => {
      toast.success(t('planning.toast_saved'));
      queryClient.invalidateQueries({ queryKey: ['saved-views'] });
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => savedViewsApi.remove(id),
    onSuccess: () => {
      toast.success(t('planning.toast_deleted'));
      queryClient.invalidateQueries({ queryKey: ['saved-views'] });
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  const openBoard = (params: Record<string, string>) => {
    const qs = new URLSearchParams(params).toString();
    navigate(qs ? `/board?${qs}` : '/board');
  };

  const saveShortcut = (name: string, params: Record<string, string>) => {
    createMutation.mutate({
      name,
      route: '/board',
      query_json: boardQuery(params),
    });
  };

  return (
    <div className="space-y-6">
      <PageHeader title={t('planning.title')} description={t('planning.subtitle')} />

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={t('planning.rules_title')}>
          <p className="mb-4 text-sm text-slate-600 dark:text-slate-400">
            {t('planning.rules_hint')}
          </p>
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => openBoard({ min_rotting_days: '10' })}
              >
                {t('planning.preset_stale10')}
                <ExternalLink className="ml-1 h-3.5 w-3.5 opacity-60" aria-hidden />
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => openBoard({ min_open_tasks: '1' })}
              >
                {t('planning.preset_tasks')}
              </Button>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => openBoard({ deal_health_risk: 'high_risk' })}
              >
                {t('planning.preset_high_risk')}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => openBoard({ deal_health_risk: 'at_risk' })}
              >
                {t('planning.preset_at_risk')}
              </Button>
            </div>
            <p className="pt-2 text-xs text-slate-500 dark:text-slate-400">
              {t('planning.deal_health_note')}
            </p>
            <div className="mt-2 flex flex-wrap gap-2 border-t border-slate-100 pt-3 dark:border-slate-800">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                loading={createMutation.isPending}
                onClick={() =>
                  saveShortcut(t('planning.preset_stale10'), { min_rotting_days: '10' })
                }
              >
                {t('planning.save_stale10')}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                loading={createMutation.isPending}
                onClick={() =>
                  saveShortcut(t('planning.preset_high_risk'), { deal_health_risk: 'high_risk' })
                }
              >
                {t('planning.save_high_risk')}
              </Button>
            </div>
          </div>
        </Card>

        <Card title={t('planning.segments_title')}>
          <p className="mb-4 text-sm text-slate-600 dark:text-slate-400">
            {t('planning.segments_hint')}
          </p>
          <Link
            to="/engagement/segments"
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-800 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-100 dark:hover:bg-slate-800"
          >
            <UsersRound className="h-4 w-4 text-honeywell-red" aria-hidden />
            {t('planning.link_segments')}
          </Link>
        </Card>
      </div>

      <Card title={t('planning.saved_views_heading')}>
        {isLoading ? (
          <Skeleton variant="line" count={4} />
        ) : views.length === 0 ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">{t('planning.empty_views')}</p>
        ) : (
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {views.map((v: SavedView) => {
              let params: Record<string, string> = {};
              try {
                params = JSON.parse(v.query_json || '{}') as Record<string, string>;
              } catch {
                params = {};
              }
              return (
                <li key={v.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                  <div>
                    <p className="text-sm font-semibold text-slate-900 dark:text-white">{v.name}</p>
                    <p className="text-xs text-slate-500">
                      {v.route}
                      {v.query_json && v.query_json !== '{}' ? ` · ${v.query_json}` : ''}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      variant="secondary"
                      onClick={() => openBoard(params)}
                    >
                      <LayoutGrid className="mr-1 h-3.5 w-3.5" aria-hidden />
                      {t('planning.open_board')}
                    </Button>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      disabled={deleteMutation.isPending}
                      onClick={() => deleteMutation.mutate(v.id)}
                      aria-label={t('planning.delete')}
                    >
                      <Trash2 className="h-4 w-4 text-red-600" aria-hidden />
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Card>
    </div>
  );
}
