import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Search, ShieldAlert, ArrowRight, Filter, RefreshCw, Plus } from 'lucide-react';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { SavedViewsBar } from '../../components/ui/SavedViewsBar';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { Modal } from '../../components/ui/Modal';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { customersApi, dealHealthApi, opportunitiesApi } from '../../lib/api';
import { onOpportunityChanged } from '../../lib/cacheInvalidation';
import { formatCurrency, formatDate } from '../../lib/formatters';
import { useT } from '../../hooks/useT';

import type { Customer, Opportunity, PaginatedResponse } from '../../lib/types';

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

interface CreateOppForm {
  title: string;
  customer_id: string;
  stage: string;
  amount: string;
  currency: string;
  close_date: string;
}

const INITIAL_CREATE_FORM: CreateOppForm = {
  title: '',
  customer_id: '',
  stage: 'prospecting',
  amount: '',
  currency: 'TRY',
  close_date: '',
};

export default function OpportunitiesHomePage() {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [query, setQuery] = useState('');
  const [stage, setStage] = useState<StageFilter>('all');
  const [limit, setLimit] = useState(50);
  // R7-FORM-1 — pre-fix the SPA had no standalone "Create Opportunity"
  // form anywhere; reps had to fake-create a Lead and convert it to
  // mint an expansion deal on an existing customer.
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState<CreateOppForm>(INITIAL_CREATE_FORM);
  const [customerSearch, setCustomerSearch] = useState('');

  const customerResults = useQuery<PaginatedResponse<Customer>>({
    queryKey: ['opp-create-customer-search', customerSearch],
    queryFn: () => customersApi.getCustomers({ search: customerSearch, page_size: 10 }),
    enabled: createOpen && customerSearch.length >= 2,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => opportunitiesApi.create(payload),
    onSuccess: (created: Opportunity) => {
      toast.success('Fırsat oluşturuldu');
      onOpportunityChanged(queryClient, created.id);
      setCreateOpen(false);
      setCreateForm(INITIAL_CREATE_FORM);
      setCustomerSearch('');
      navigate(`/opportunities/${created.id}`);
    },
    onError: () => toast.error('Fırsat oluşturulamadı'),
  });

  const handleCreate = () => {
    if (!createForm.title.trim()) {
      toast.error(t('opps.home.title_required'));
      return;
    }
    const payload: Record<string, unknown> = {
      title: createForm.title.trim(),
      stage: createForm.stage,
      currency: createForm.currency,
    };
    if (createForm.customer_id) payload.customer_id = Number(createForm.customer_id);
    if (createForm.amount.trim()) payload.amount = parseFloat(createForm.amount);
    if (createForm.close_date) payload.close_date = createForm.close_date;
    createMutation.mutate(payload);
  };

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
      // R7-TS-7 — backend nests customer name under `o.customer.name`;
      // the previous flat `customer_name` cast was always undefined.
      const customerHay = `${o.customer?.name ?? ''} ${o.customer?.company ?? ''}`;
      const hay = `${o.title || ''} ${customerHay}`.toLowerCase();
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
            {t('common.refresh')}
          </Button>
          <Button variant="secondary" onClick={() => navigate('/board')}>
            <ArrowRight size={16} />
            Kanban’a Git
          </Button>
          {/* R7-FORM-1 — Yeni Fırsat (was missing entirely). */}
          <Button variant="primary" onClick={() => setCreateOpen(true)}>
            <Plus size={16} />
            {t('opps.home.new_opportunity')}
          </Button>
        </div>
      </PageHeader>

      {/* S-E saved views — universal */}
      <div className="mb-3">
        <SavedViewsBar
          route="/opportunities"
          queryJson={JSON.stringify({ query, stage, limit })}
          onApply={(view) => {
            try {
              const payload = JSON.parse(view.query_json) as {
                query?: string;
                stage?: string;
                limit?: number;
              };
              const VALID_STAGES = [
                'all',
                'prospecting',
                'qualified',
                'proposal',
                'negotiation',
                'closed_won',
                'closed_lost',
              ] as const;
              if (typeof payload.query === 'string') setQuery(payload.query);
              if (
                typeof payload.stage === 'string' &&
                (VALID_STAGES as readonly string[]).includes(payload.stage)
              ) {
                setStage(payload.stage as StageFilter);
              }
              if (typeof payload.limit === 'number') setLimit(payload.limit);
            } catch {
              /* ignore malformed view */
            }
          }}
        />
      </div>

      {/* Top widgets */}
      <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card className="overflow-hidden">
          <div className="p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">
                  {t('opps.home.widget_all')}
                </p>
                <p className="mt-1 text-2xl font-bold text-slate-900 dark:text-white">
                  {oppsQuery.isLoading ? '—' : String(oppsQuery.data?.total ?? filtered.length)}
                </p>
              </div>
              <div className="rounded-xl bg-slate-100 px-3 py-2 text-sm font-semibold text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                {t('opps.home.widget_all_badge')}
              </div>
            </div>
            <div className="mt-3 text-sm text-slate-500">{t('opps.home.widget_all_hint')}</div>
          </div>
        </Card>

        <Card className="overflow-hidden">
          <div className="p-5">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase">
                  {t('opps.home.widget_risky')}
                </p>
                <p className="mt-1 text-2xl font-bold text-slate-900 dark:text-white">
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
              <div className="text-sm text-slate-500">{t('opps.home.widget_risky_hint')}</div>
              <Button variant="secondary" onClick={() => navigate('/at-risk')}>
                {t('opps.home.widget_risky_cta')}
                <ArrowRight size={16} />
              </Button>
            </div>
          </div>
        </Card>

        <Card className="overflow-hidden">
          <div className="p-5">
            <p className="text-xs font-semibold text-slate-500 uppercase">
              {t('opps.home.widget_value')}
            </p>
            <div className="mt-1 text-2xl font-bold text-slate-900 dark:text-white">
              {oppsQuery.isLoading
                ? '—'
                : formatCurrency(
                    filtered.reduce((s, o) => s + Number(o.amount || 0), 0),
                    filtered[0]?.currency || 'TRY',
                  )}
            </div>
            <div className="mt-3 text-sm text-slate-500">{t('opps.home.widget_value_hint')}</div>
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
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder={t('opps.home.search_placeholder')}
                className="w-full rounded-xl border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm text-slate-900 shadow-sm outline-none focus:ring-2 focus:ring-blue-500 dark:border-slate-800 dark:bg-slate-900 dark:text-white"
              />
            </div>

            <div className="hidden items-center gap-2 md:flex">
              <Filter size={16} className="text-slate-400" />
              <select
                value={stage}
                onChange={(e) => setStage(e.target.value as StageFilter)}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-900"
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
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-900"
              >
                <option value={25}>25</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
          </div>

          <div className="text-sm text-slate-500">
            {t('opps.home.showing')}{' '}
            <span className="font-semibold text-slate-900 dark:text-white">{filtered.length}</span>
          </div>
        </div>
      </Card>

      {/* List */}
      {oppsQuery.isLoading ? (
        <Skeleton variant="card" count={6} />
      ) : oppsQuery.isError ? (
        // Round-15 Sprint 15i — standardized banner with retry. Pre-fix
        // the page rendered a static red-text Card with no recovery
        // affordance.
        <QueryErrorBanner variant="block" onRetry={() => oppsQuery.refetch()} />
      ) : filtered.length === 0 ? (
        <EmptyState title={t('opps.home.empty_title')} description={t('opps.home.empty_desc')} />
      ) : (
        <div className="space-y-3">
          {filtered.map((o) => (
            <Card key={o.id} className="overflow-hidden">
              <button
                type="button"
                onClick={() => navigate(`/opportunities/${o.id}`)}
                className="flex w-full items-start justify-between gap-4 p-4 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/50"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="font-medium text-slate-900 dark:text-white truncate">
                      {o.title}
                    </h3>
                    <Badge variant={stageVariant(o.stage) as never} size="sm">
                      {stageLabel(o.stage)}
                    </Badge>
                    {/* Forecast classification — drives commit/best-case
                        rollups in the forecast view. Only render when
                        the manager has set it. */}
                    {o.forecast_category && (
                      <Badge
                        variant={
                          o.forecast_category === 'commit'
                            ? 'success'
                            : o.forecast_category === 'best_case'
                              ? 'info'
                              : 'default'
                        }
                        size="sm"
                      >
                        {o.forecast_category === 'commit'
                          ? 'Taahhüt'
                          : o.forecast_category === 'best_case'
                            ? 'En İyi Senaryo'
                            : o.forecast_category === 'pipeline'
                              ? 'Pipeline'
                              : 'Hariç'}
                      </Badge>
                    )}
                    {/* Probability badge — backend stores 0-100. Hide
                        when 0/null since that's just the default. */}
                    {typeof o.probability === 'number' && o.probability > 0 && (
                      <span className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] tabular-nums text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        %{Math.round(o.probability)}
                      </span>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap gap-3 text-sm text-slate-500">
                    <span>{formatCurrency(Number(o.amount || 0), o.currency || 'TRY')}</span>
                    {/* R7-TS-7 — backend nests customer.name; pre-fix the
                        SPA was reading a flat `customer_name` that the
                        backend never emits. */}
                    {o.customer?.name && (
                      <span className="truncate">{o.customer.company || o.customer.name}</span>
                    )}
                    {/* Close date — fetched but never rendered before
                        audit F-15. Critical "this deal closes Friday"
                        signal. */}
                    {o.close_date && (
                      <span className="text-slate-500">⏱ {formatDate(o.close_date)}</span>
                    )}
                    {/* Rotting indicator — shows in red when the deal
                        has been stale for more than a week.
                        R7-TS-7 — Opportunity.rotting_days is required on
                        the type, so no cast needed. */}
                    {typeof o.rotting_days === 'number' && o.rotting_days > 7 && (
                      <span className="font-medium text-rose-600 dark:text-rose-400">
                        🥀 {o.rotting_days}g durgun
                      </span>
                    )}
                    {/* Revenue-leak diff: when an open deal has a
                        previous_amount that differs from the current
                        amount, surface the slip.
                        R6-RENDER-7 — Opportunity.previous_amount has been
                        on the TS type since R5-TS-9; the unsafe cast was
                        leftover from before that. */}
                    {o.previous_amount != null &&
                      Number(o.previous_amount) !== Number(o.amount || 0) && (
                        <span className="text-amber-600 dark:text-amber-400">
                          {formatCurrency(Number(o.previous_amount), o.currency || 'TRY')} →{' '}
                          {formatCurrency(Number(o.amount || 0), o.currency || 'TRY')}
                        </span>
                      )}
                    {/* Closed-lost reason badge — surfaces the manual
                        loss reason when the opportunity is closed_lost
                        so reps can see "neden kaybedildi" at a glance. */}
                    {/* Round-8 R8-COND-1 — backend uses status='closed_lost', not 'closed'. */}
                    {o.status === 'closed_lost' && o.loss_reason && (
                      <span className="truncate text-rose-600 dark:text-rose-400">
                        Kayıp: {o.loss_reason}
                      </span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 text-slate-400">
                  <ArrowRight size={16} />
                </div>
              </button>
            </Card>
          ))}
        </div>
      )}

      {/* R7-FORM-1 — Create Opportunity modal. Backend OpportunityCreate
          accepts title, stage, amount, currency, close_date, customer_id.
          Pre-fix this form did not exist and OpportunityCreate was
          unreachable from the SPA. */}
      <Modal
        isOpen={createOpen}
        onClose={() => {
          setCreateOpen(false);
          setCreateForm(INITIAL_CREATE_FORM);
          setCustomerSearch('');
        }}
        title={t('opps.home.new_opportunity')}
        size="lg"
      >
        <div className="space-y-4">
          <Input
            label={t('common.title_label')}
            value={createForm.title}
            onChange={(e) => setCreateForm((p) => ({ ...p, title: e.target.value }))}
            placeholder="Honeywell servis genişletme"
            required
          />
          <div>
            <label className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300">
              {t('common.customer_label')}
            </label>
            <Input
              placeholder={t('common.search_customer_by_name')}
              value={customerSearch}
              onChange={(e) => {
                setCustomerSearch(e.target.value);
                if (createForm.customer_id) {
                  setCreateForm((p) => ({ ...p, customer_id: '' }));
                }
              }}
            />
            {customerSearch.length >= 2 &&
              !createForm.customer_id &&
              (customerResults.data?.items?.length ?? 0) > 0 && (
                <div
                  className="mt-1 max-h-48 overflow-y-auto rounded-lg border bg-white shadow-sm dark:bg-slate-900"
                  style={{ borderColor: 'var(--border)' }}
                >
                  {(customerResults.data?.items ?? []).map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800"
                      onClick={() => {
                        setCreateForm((p) => ({ ...p, customer_id: String(c.id) }));
                        setCustomerSearch(`${c.name}${c.company ? ` · ${c.company}` : ''}`);
                      }}
                    >
                      <span className="font-medium">{c.name}</span>
                      {c.company && <span className="ml-2 text-slate-500">{c.company}</span>}
                    </button>
                  ))}
                </div>
              )}
            {createForm.customer_id && (
              <p className="mt-1 text-[12px] text-slate-500">
                Seçildi: müşteri #{createForm.customer_id}
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300">
                Aşama
              </label>
              <select
                value={createForm.stage}
                onChange={(e) => setCreateForm((p) => ({ ...p, stage: e.target.value }))}
                className="block w-full rounded-[12px] border px-3 py-2 text-sm"
                style={{
                  borderColor: 'var(--border)',
                  backgroundColor: 'var(--surface)',
                  color: 'var(--text-primary)',
                }}
              >
                <option value="prospecting">Prospecting</option>
                <option value="qualified">Qualified</option>
                <option value="proposal">Proposal</option>
                <option value="negotiation">Negotiation</option>
                <option value="closed_won">Closed Won</option>
                <option value="closed_lost">Closed Lost</option>
              </select>
            </div>
            <Input
              label="Kapanış tarihi"
              type="date"
              value={createForm.close_date}
              onChange={(e) => setCreateForm((p) => ({ ...p, close_date: e.target.value }))}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Tutar"
              type="number"
              min={0}
              step="0.01"
              value={createForm.amount}
              onChange={(e) => setCreateForm((p) => ({ ...p, amount: e.target.value }))}
              placeholder="0.00"
            />
            <div>
              <label className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300">
                Para birimi
              </label>
              <select
                value={createForm.currency}
                onChange={(e) => setCreateForm((p) => ({ ...p, currency: e.target.value }))}
                className="block w-full rounded-[12px] border px-3 py-2 text-sm"
                style={{
                  borderColor: 'var(--border)',
                  backgroundColor: 'var(--surface)',
                  color: 'var(--text-primary)',
                }}
              >
                <option value="TRY">TRY</option>
                <option value="USD">USD</option>
                <option value="EUR">EUR</option>
              </select>
            </div>
          </div>
          <div
            className="flex justify-end gap-2 border-t pt-3"
            style={{ borderColor: 'var(--border)' }}
          >
            <Button variant="secondary" onClick={() => setCreateOpen(false)}>
              İptal
            </Button>
            <Button onClick={handleCreate} loading={createMutation.isPending}>
              Oluştur
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
