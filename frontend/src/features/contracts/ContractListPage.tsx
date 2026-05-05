import { useState, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { FileSignature, AlertTriangle, FileCheck, Wallet, RefreshCcw } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { Modal } from '../../components/ui/Modal';
import { contractsApi, customersApi } from '../../lib/api';
import type { Contract, Customer } from '../../lib/types';
import { useT } from '../../hooks/useT';
import { CONTRACT_STATUS_VALUES, translateContractStatus } from '../../lib/labelTranslations';
import { formatDate, currentLocale } from '../../lib/formatters';

/**
 * KpiTile — KPI summary card. See InvoiceListPage for the canonical
 * implementation; this one mirrors the layout for consistency.
 */
function KpiTile({
  icon,
  label,
  value,
  tone = 'default',
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  tone?: 'default' | 'positive' | 'negative';
}) {
  const valueClass =
    tone === 'positive'
      ? 'text-emerald-600 dark:text-emerald-400'
      : tone === 'negative'
        ? 'text-red-600 dark:text-red-400'
        : 'text-slate-900 dark:text-white';
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center gap-2">
        <span className="inline-flex h-7 w-7 items-center justify-center rounded-[10px] bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
          {icon}
        </span>
        <p className="text-overline text-slate-500 dark:text-slate-400">{label}</p>
      </div>
      <p
        className={`mt-2.5 text-[22px] font-bold leading-none tracking-tight tabular-nums ${valueClass}`}
      >
        {value}
      </p>
    </div>
  );
}

// Map contract status → Badge variant. Uses the design-system tone scale
// instead of bespoke class strings.
type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'default';
const STATUS_TONE: Record<string, BadgeTone> = {
  draft: 'default',
  active: 'success',
  amended: 'warning',
  expired: 'danger',
  terminated: 'danger',
};

export default function ContractListPage() {
  const t = useT();
  const locale = currentLocale();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'all' | 'expiring'>('all');

  // Create form state
  const [formTitle, setFormTitle] = useState('');
  const [formCustomerId, setFormCustomerId] = useState<number | null>(null);
  const [formCustomerSearch, setFormCustomerSearch] = useState('');
  const [formStartDate, setFormStartDate] = useState('');
  const [formEndDate, setFormEndDate] = useState('');
  const [formValue, setFormValue] = useState('');

  const { data: contractsData, isLoading } = useQuery({
    queryKey: ['contracts', statusFilter, search],
    queryFn: () =>
      contractsApi.list({
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(search ? { search } : {}),
      }),
  });

  const { data: expiringData } = useQuery({
    queryKey: ['contracts-expiring'],
    queryFn: () => contractsApi.expiring(30),
  });

  const { data: customerResults } = useQuery<{ items: Customer[] }>({
    queryKey: ['customers-search', formCustomerSearch],
    queryFn: () => customersApi.getCustomers({ search: formCustomerSearch, page_size: 10 }),
    enabled: formCustomerSearch.length >= 2,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => contractsApi.create(payload),
    onSuccess: (data) => {
      toast.success(t('contracts.toast_created'));
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
      setIsCreateOpen(false);
      resetForm();
      navigate(`/contracts/${(data as Contract).id}`);
    },
    onError: () => toast.error(t('contracts.toast_create_failed')),
  });

  const resetForm = useCallback(() => {
    setFormTitle('');
    setFormCustomerId(null);
    setFormCustomerSearch('');
    setFormStartDate('');
    setFormEndDate('');
    setFormValue('');
  }, []);

  const handleCreate = useCallback(() => {
    if (!formTitle || !formCustomerId) {
      toast.error(t('contracts.err_title_customer'));
      return;
    }
    createMutation.mutate({
      customer_id: formCustomerId,
      title: formTitle,
      start_date: formStartDate || undefined,
      end_date: formEndDate || undefined,
      value: formValue ? parseFloat(formValue) : undefined,
    });
  }, [formTitle, formCustomerId, formStartDate, formEndDate, formValue, createMutation, t]);

  // Backend canonicalized to {items,total,page,page_size,pages} in
  // audit A-6 + Round-5 Phase 7; keep legacy fallbacks for in-flight
  // responses mid-deploy.
  const contracts: Contract[] = contractsData?.items || contractsData?.contracts || [];
  const expiringContracts: Contract[] =
    expiringData?.items || expiringData?.contracts || [];
  const expiringCount = expiringData?.total ?? expiringData?.count ?? 0;

  const statusOptions = useMemo(
    () => [
      { value: '', label: t('labels.all') },
      ...CONTRACT_STATUS_VALUES.map((value) => ({
        value,
        label: translateContractStatus(value, t),
      })),
    ],
    [t],
  );

  const tabs = [
    {
      value: 'all' as const,
      label: t('contracts.tab_all'),
      count: undefined as number | undefined,
    },
    { value: 'expiring' as const, label: t('contracts.tab_expiring'), count: expiringCount },
  ];

  // KPI summary — derived from active and expiring lists.
  const summary = useMemo(() => {
    const active = contracts.filter((c) => c.status === 'active').length;
    const totalValue = contracts
      .filter((c) => c.status !== 'terminated' && c.status !== 'expired')
      .reduce((sum, c) => sum + (c.value ?? 0), 0);
    return {
      active,
      expiring: expiringCount,
      totalValue,
      total: contracts.length,
    };
  }, [contracts, expiringCount]);

  return (
    <div>
      <PageHeader title={t('contracts.title')} description={t('contracts.description')}>
        <Button onClick={() => setIsCreateOpen(true)}>
          <FileSignature size={14} />
          {t('contracts.new')}
        </Button>
      </PageHeader>

      {/* KPI summary strip */}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiTile
          icon={<FileCheck size={14} />}
          label="Aktif Kontrat"
          value={String(summary.active)}
        />
        <KpiTile
          icon={<AlertTriangle size={14} />}
          label="Yakında Bitecek"
          value={String(summary.expiring)}
          tone={summary.expiring > 0 ? 'negative' : 'default'}
        />
        <KpiTile
          icon={<Wallet size={14} />}
          label="Toplam Değer"
          value={summary.totalValue.toLocaleString(locale, { minimumFractionDigits: 0 })}
        />
        <KpiTile
          icon={<RefreshCcw size={14} />}
          label="Toplam Kontrat"
          value={String(summary.total)}
        />
      </div>

      {/* Segmented tabs with count chip on the expiring tab */}
      <div
        className="mb-4 inline-flex flex-wrap gap-1 rounded-[12px] border border-slate-200 bg-slate-50/80 p-1 dark:border-slate-800 dark:bg-slate-900/40"
        role="tablist"
        aria-label={t('contracts.title')}
      >
        {tabs.map((tab) => {
          const isActive = activeTab === tab.value;
          return (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setActiveTab(tab.value)}
              className={[
                'inline-flex h-8 items-center gap-2 rounded-[10px] px-3 text-[13px] font-medium transition-all',
                'focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20',
                isActive
                  ? 'bg-white text-slate-900 shadow-(--shadow-xs) dark:bg-slate-800 dark:text-white'
                  : 'text-slate-600 hover:bg-white/60 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200',
              ].join(' ')}
            >
              {tab.label}
              {tab.count != null && tab.count > 0 && (
                <span
                  className={[
                    'inline-flex h-5 min-w-[22px] items-center justify-center rounded-full px-1.5 text-[10px] font-bold tabular-nums ring-1 ring-inset',
                    isActive
                      ? 'bg-honeywell-red/10 text-honeywell-red ring-honeywell-red/20'
                      : 'bg-slate-100 text-slate-700 ring-slate-200 dark:bg-slate-800 dark:text-slate-200 dark:ring-slate-700',
                  ].join(' ')}
                >
                  {tab.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {activeTab === 'all' && (
        <>
          {/* Filters */}
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <div className="w-52">
              <Select
                label={t('contracts.filter_status')}
                options={statusOptions}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              />
            </div>
            <div className="w-72">
              <Input
                label={t('contracts.search_label')}
                placeholder={t('contracts.search_ph')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>

          {isLoading && <Skeleton variant="table" />}

          {!isLoading && contracts.length === 0 && (
            <div className="rounded-2xl border border-slate-200 bg-white py-2 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
              <EmptyState
                variant="default"
                icon={<FileSignature size={20} />}
                title={t('contracts.empty')}
                action={
                  <Button onClick={() => setIsCreateOpen(true)} variant="secondary">
                    <FileSignature size={14} />
                    {t('contracts.new')}
                  </Button>
                }
              />
            </div>
          )}

          {!isLoading && contracts.length > 0 && (
            <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-900/40">
                      <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                        {t('contracts.col_title')}
                      </th>
                      <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                        {t('contracts.col_status')}
                      </th>
                      <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                        {t('contracts.col_start')}
                      </th>
                      <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                        {t('contracts.col_end')}
                      </th>
                      <th className="px-4 py-3 text-right text-overline text-slate-500 dark:text-slate-400">
                        {t('contracts.col_value')}
                      </th>
                      <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                        {t('contracts.col_created')}
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {contracts.map((contract) => (
                      <tr
                        key={contract.id}
                        onClick={() => navigate(`/contracts/${contract.id}`)}
                        className="cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
                      >
                        <td className="px-4 py-3 text-[13px] font-semibold text-slate-900 dark:text-white">
                          {contract.title}
                        </td>
                        <td className="px-4 py-3">
                          <Badge variant={STATUS_TONE[contract.status] ?? 'default'} size="sm" dot>
                            {translateContractStatus(contract.status, t)}
                          </Badge>
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
                          {contract.start_date ? formatDate(contract.start_date, locale) : '—'}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
                          {contract.end_date ? formatDate(contract.end_date, locale) : '—'}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-right text-[13px] font-semibold tabular-nums text-slate-900 dark:text-white">
                          {contract.value != null
                            ? contract.value.toLocaleString(locale, { minimumFractionDigits: 2 })
                            : '—'}
                        </td>
                        <td className="whitespace-nowrap px-4 py-3 text-[12px] tabular-nums text-slate-400 dark:text-slate-500">
                          {contract.created_at ? formatDate(contract.created_at, locale) : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {activeTab === 'expiring' && (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center gap-2.5 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-[10px] bg-amber-100 text-amber-700 ring-1 ring-inset ring-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-900/60">
              <AlertTriangle size={14} />
            </span>
            <h3 className="text-[14px] font-semibold text-slate-900 dark:text-white">
              {t('contracts.expiring_title')}
            </h3>
          </div>
          {expiringContracts.length === 0 ? (
            <EmptyState
              variant="compact"
              icon={<AlertTriangle size={18} />}
              title={t('contracts.expiring_empty')}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-900/40">
                    <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                      {t('contracts.col_title')}
                    </th>
                    <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                      {t('contracts.col_end_date')}
                    </th>
                    <th className="px-4 py-3 text-right text-overline text-slate-500 dark:text-slate-400">
                      {t('contracts.col_value')}
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {expiringContracts.map((contract) => (
                    <tr
                      key={contract.id}
                      onClick={() => navigate(`/contracts/${contract.id}`)}
                      className="cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
                    >
                      <td className="px-4 py-3 text-[13px] font-semibold text-slate-900 dark:text-white">
                        {contract.title}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-[13px] font-medium tabular-nums text-red-600 dark:text-red-400">
                        {contract.end_date || '—'}
                      </td>
                      <td className="whitespace-nowrap px-4 py-3 text-right text-[13px] font-semibold tabular-nums text-slate-900 dark:text-white">
                        {contract.value != null
                          ? contract.value.toLocaleString(locale, { minimumFractionDigits: 2 })
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Create Modal — switched from bespoke overlay to Modal primitive
          so focus trap, escape key, and shadow tokens are consistent. */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => {
          setIsCreateOpen(false);
          resetForm();
        }}
        title={t('contracts.modal_create_title')}
        size="md"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setIsCreateOpen(false);
                resetForm();
              }}
            >
              {t('common.cancel')}
            </Button>
            <Button onClick={handleCreate} loading={createMutation.isPending}>
              {t('contracts.create')}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label={t('contracts.label_title')}
            value={formTitle}
            onChange={(e) => setFormTitle(e.target.value)}
            placeholder={t('contracts.title_ph')}
          />
          <div className="relative">
            <Input
              label={t('contracts.label_customer')}
              value={formCustomerSearch}
              onChange={(e) => {
                setFormCustomerSearch(e.target.value);
                if (formCustomerId) setFormCustomerId(null);
              }}
              placeholder={t('contracts.customer_search_ph')}
            />
            {customerResults?.items &&
              customerResults.items.length > 0 &&
              formCustomerSearch.length >= 2 &&
              !formCustomerId && (
                <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-[12px] border border-slate-200 bg-white shadow-(--shadow-lg) dark:border-slate-700 dark:bg-slate-800">
                  <ul className="max-h-44 divide-y divide-slate-100 overflow-y-auto dark:divide-slate-700">
                    {customerResults.items.map((c) => (
                      <li key={c.id}>
                        <button
                          type="button"
                          onClick={() => {
                            setFormCustomerId(c.id);
                            setFormCustomerSearch(c.company || c.name);
                          }}
                          className="flex w-full items-baseline gap-2 px-3.5 py-2.5 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-700/60"
                        >
                          <span className="text-[13px] font-medium text-slate-900 dark:text-white">
                            {c.company || c.name}
                          </span>
                          {c.email && (
                            <span className="truncate text-[12px] text-slate-500 dark:text-slate-400">
                              {c.email}
                            </span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            {formCustomerId && (
              <p className="mt-1.5 text-[12px] font-medium text-emerald-600 dark:text-emerald-400">
                {t('invoices.selected_id') ?? 'Seçildi'}: #{formCustomerId}
              </p>
            )}
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Input
              label={t('contracts.label_start_date')}
              type="date"
              value={formStartDate}
              onChange={(e) => setFormStartDate(e.target.value)}
            />
            <Input
              label={t('contracts.label_end_date')}
              type="date"
              value={formEndDate}
              onChange={(e) => setFormEndDate(e.target.value)}
            />
          </div>
          <Input
            label={t('contracts.label_value')}
            type="number"
            min={0}
            step={0.01}
            value={formValue}
            onChange={(e) => setFormValue(e.target.value)}
            placeholder={t('contracts.value_ph')}
          />
        </div>
      </Modal>
    </div>
  );
}
