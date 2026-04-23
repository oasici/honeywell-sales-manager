import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Search, ShieldAlert, ArrowRight, Filter, RefreshCw } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { opportunitiesApi, dealHealthApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import { useT } from '../../hooks/useT';

import type { Opportunity } from '../../lib/types';

type StageFilter =
  | 'all'
  | 'prospecting'
  | 'qualified'
  | 'proposal'
  | 'negotiation'
  | 'closed_won'
  | 'closed_lost';

function stageLabel(stage?: string) {
  const s = (stage || '').toLowerCase();
  if (s === 'prospecting') return 'Prospecting';
  if (s === 'qualified') return 'Qualified';
  if (s === 'proposal') return 'Proposal';
  if (s === 'negotiation') return 'Negotiation';
  if (s === 'closed_won') return 'Closed Won';
  if (s === 'closed_lost') return 'Closed Lost';
  return stage || '-';
}

function stageVariant(stage?: string) {
  const s = (stage || '').toLowerCase();
  if (s === 'closed_won') return 'success';
  if (s === 'closed_lost') return 'danger';
  if (s === 'negotiation') return 'warning';
  if (s === 'proposal') return 'info';
  return 'default';
}

export default function OpportunitiesHomePage() {
  const t = useT();
  const navigate = useNavigate();

  const [query, setQuery] = useState('');
  const [stage, setStage] = useState<StageFilter>('all');
  const [limit, setLimit] = useState(50);

  const oppsQuery = useQuery({
    queryKey: ['opportunities-home', { query, stage, limit }],
    queryFn: async () => {
      const params: Record<string, unknown> = { limit };
      // Backend list endpoint supports filters; we keep it conservative here.
      if (stage !== 'all') params.stage = stage;
      const res = await opportunitiesApi.list(params);
      return res as { items: Opportunity[]; total: number };
    },
  });

  const riskyQuery = useQuery({
    queryKey: ['opportunities-home-risky', 40],
    queryFn: () => dealHealthApi.getAtRisk(40),
  });

  const filtered = useMemo(() => {
    const items = (oppsQuery.data?.items ?? []) as Opportunity[];
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((o) => {
      const hay =
        `${o.title || ''} ${String((o as unknown as { customer_name?: string }).customer_name || '')}`.toLowerCase();
      return hay.includes(q);
    });
  }, [oppsQuery.data, query]);

  return (
    <div>
      <PageHeader title={t('opps.home.title')} description={t('opps.home.desc')}>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => oppsQuery.refetch()}
            disabled={oppsQuery.isFetching}
          >
            <RefreshCw size={16} />
            Yenile
          </Button>
          <Button variant="primary" onClick={() => navigate('/board')}>
            <ArrowRight size={16} />
            Kanban’a Git
          </Button>
        </div>
      </PageHeader>

      {/* Top widgets */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="overflow-hidden">
          <div className="p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase">
                  {t('opps.home.widget_all')}
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
                  {oppsQuery.isLoading ? '—' : String(oppsQuery.data?.total ?? filtered.length)}
                </p>
              </div>
              <div className="rounded-xl bg-gray-100 px-3 py-2 text-sm font-semibold text-gray-700 dark:bg-gray-800 dark:text-gray-200">
                {t('opps.home.widget_all_badge')}
              </div>
            </div>
            <div className="mt-3 text-sm text-gray-500">{t('opps.home.widget_all_hint')}</div>
          </div>
        </Card>

        <Card className="overflow-hidden">
          <div className="p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase">
                  {t('opps.home.widget_risky')}
                </p>
                <p className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
                  {riskyQuery.isLoading
                    ? '—'
                    : String((riskyQuery.data as { count?: number })?.count ?? 0)}
                </p>
              </div>
              <div className="rounded-xl bg-red-50 px-3 py-2 text-sm font-semibold text-red-700 dark:bg-red-900/20 dark:text-red-200">
                <ShieldAlert size={16} className="inline-block mr-1 -mt-0.5" />
                Eşik: 40
              </div>
            </div>
            <div className="mt-3 flex items-center justify-between gap-3">
              <div className="text-sm text-gray-500">{t('opps.home.widget_risky_hint')}</div>
              <Button variant="secondary" onClick={() => navigate('/at-risk')}>
                {t('opps.home.widget_risky_cta')}
                <ArrowRight size={16} />
              </Button>
            </div>
          </div>
        </Card>

        <Card className="overflow-hidden">
          <div className="p-5">
            <p className="text-xs font-semibold text-gray-500 uppercase">
              {t('opps.home.widget_value')}
            </p>
            <div className="mt-1 text-2xl font-bold text-gray-900 dark:text-white">
              {oppsQuery.isLoading
                ? '—'
                : formatCurrency(
                    filtered.reduce((s, o) => s + Number(o.amount || 0), 0),
                    filtered[0]?.currency || 'TRY',
                  )}
            </div>
            <div className="mt-3 text-sm text-gray-500">{t('opps.home.widget_value_hint')}</div>
          </div>
        </Card>
      </div>

      {/* Filters */}
      <Card className="mb-4">
        <div className="flex flex-col gap-3 p-4 md:flex-row md:items-center md:justify-between">
          <div className="flex flex-1 items-center gap-2">
            <div className="relative flex-1">
              <Search
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
              />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('opps.home.search_placeholder')}
                className="w-full rounded-xl border border-gray-200 bg-white py-2 pl-9 pr-3 text-sm text-gray-900 shadow-sm outline-none focus:ring-2 focus:ring-blue-500 dark:border-gray-700 dark:bg-gray-900 dark:text-white"
              />
            </div>

            <div className="hidden items-center gap-2 md:flex">
              <Filter size={16} className="text-gray-400" />
              <select
                value={stage}
                onChange={(e) => setStage(e.target.value as StageFilter)}
                className="rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-900"
              >
                <option value="all">{t('opps.home.stage_all')}</option>
                <option value="prospecting">Prospecting</option>
                <option value="qualified">Qualified</option>
                <option value="proposal">Proposal</option>
                <option value="negotiation">Negotiation</option>
                <option value="closed_won">Closed Won</option>
                <option value="closed_lost">Closed Lost</option>
              </select>
              <select
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                className="rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-900"
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
          </div>

          <div className="text-sm text-gray-500">
            {t('opps.home.showing')}{' '}
            <span className="font-semibold text-gray-900 dark:text-white">{filtered.length}</span>
          </div>
        </div>
      </Card>

      {/* List */}
      {oppsQuery.isLoading ? (
        <Skeleton variant="card" count={6} />
      ) : oppsQuery.isError ? (
        <Card>
          <div className="p-8 text-center text-red-500">{t('opps.home.load_error')}</div>
        </Card>
      ) : filtered.length === 0 ? (
        <EmptyState title={t('opps.home.empty_title')} description={t('opps.home.empty_desc')} />
      ) : (
        <div className="space-y-3">
          {filtered.map((o) => (
            <Card key={o.id} className="overflow-hidden">
              <button
                type="button"
                onClick={() => navigate(`/opportunities/${o.id}`)}
                className="flex w-full items-start justify-between gap-4 p-4 text-left transition-colors hover:bg-gray-50 dark:hover:bg-gray-800/50"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-medium text-gray-900 dark:text-white truncate">
                      {o.title}
                    </h3>
                    <Badge variant={stageVariant(o.stage) as never} size="sm">
                      {stageLabel(o.stage)}
                    </Badge>
                  </div>
                  <div className="mt-1 flex flex-wrap gap-3 text-sm text-gray-500">
                    <span>{formatCurrency(Number(o.amount || 0), o.currency || 'TRY')}</span>
                    {(o as unknown as { customer_name?: string }).customer_name ? (
                      <span className="truncate">
                        {(o as unknown as { customer_name?: string }).customer_name}
                      </span>
                    ) : null}
                  </div>
                </div>

                <div className="flex items-center gap-2 text-gray-400">
                  <ArrowRight size={16} />
                </div>
              </button>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
