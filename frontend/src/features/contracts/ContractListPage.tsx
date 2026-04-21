import { useState, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { contractsApi, customersApi } from '../../lib/api';
import type { Contract, Customer } from '../../lib/types';
import { useT } from '../../hooks/useT';
import { CONTRACT_STATUS_VALUES, translateContractStatus } from '../../lib/labelTranslations';
import { formatDate, currentLocale } from '../../lib/formatters';

const STATUS_BADGES: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  active: 'bg-green-100 text-green-700',
  amended: 'bg-yellow-100 text-yellow-700',
  expired: 'bg-red-100 text-red-700',
  terminated: 'bg-red-200 text-red-800',
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

  const contracts: Contract[] = contractsData?.contracts || [];
  const expiringContracts: Contract[] = expiringData?.contracts || [];
  const expiringCount = expiringData?.count || 0;

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

  return (
    <div>
      <PageHeader title={t('contracts.title')} description={t('contracts.description')}>
        <Button onClick={() => setIsCreateOpen(true)}>{t('contracts.new')}</Button>
      </PageHeader>

      {/* Tabs */}
      <div className="mb-4 flex gap-2">
        <button
          type="button"
          onClick={() => setActiveTab('all')}
          className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'all'
              ? 'bg-honeywell-red text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          {t('contracts.tab_all')}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('expiring')}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'expiring'
              ? 'bg-honeywell-red text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          {t('contracts.tab_expiring')}
          {expiringCount > 0 && (
            <span
              className={`flex h-5 min-w-[20px] items-center justify-center rounded-full px-1.5 text-[10px] font-bold ${
                activeTab === 'expiring'
                  ? 'bg-white text-honeywell-red'
                  : 'bg-honeywell-red text-white'
              }`}
            >
              {expiringCount}
            </span>
          )}
        </button>
      </div>

      {activeTab === 'all' && (
        <>
          {/* Filters */}
          <div className="mb-4 flex flex-wrap gap-3">
            <div className="w-48">
              <Select
                label={t('contracts.filter_status')}
                options={statusOptions}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              />
            </div>
            <div className="w-64">
              <Input
                label={t('contracts.search_label')}
                placeholder={t('contracts.search_ph')}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>

          {isLoading && <Skeleton variant="card" count={3} />}

          {!isLoading && contracts.length === 0 && (
            <Card>
              <p className="py-8 text-center text-sm text-gray-500">{t('contracts.empty')}</p>
            </Card>
          )}

          {!isLoading && contracts.length > 0 && (
            <Card>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50">
                      <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                        {t('contracts.col_title')}
                      </th>
                      <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                        {t('contracts.col_status')}
                      </th>
                      <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                        {t('contracts.col_start')}
                      </th>
                      <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                        {t('contracts.col_end')}
                      </th>
                      <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                        {t('contracts.col_value')}
                      </th>
                      <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                        {t('contracts.col_created')}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {contracts.map((contract) => (
                      <tr
                        key={contract.id}
                        onClick={() => navigate(`/contracts/${contract.id}`)}
                        className="cursor-pointer border-b border-gray-100 hover:bg-gray-50 transition-colors"
                      >
                        <td className="px-3 py-2 font-medium text-gray-900">{contract.title}</td>
                        <td className="px-3 py-2">
                          <span
                            className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGES[contract.status] || 'bg-gray-100 text-gray-700'}`}
                          >
                            {translateContractStatus(contract.status, t)}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-gray-600">
                          {contract.start_date ? formatDate(contract.start_date, locale) : '-'}
                        </td>
                        <td className="px-3 py-2 text-gray-600">
                          {contract.end_date ? formatDate(contract.end_date, locale) : '-'}
                        </td>
                        <td className="px-3 py-2 text-right font-medium text-gray-900">
                          {contract.value != null
                            ? contract.value.toLocaleString(locale, { minimumFractionDigits: 2 })
                            : '-'}
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-400">
                          {contract.created_at ? formatDate(contract.created_at, locale) : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}

      {activeTab === 'expiring' && (
        <Card title={t('contracts.expiring_title')}>
          {expiringContracts.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-500">
              {t('contracts.expiring_empty')}
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                      {t('contracts.col_title')}
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                      {t('contracts.col_end_date')}
                    </th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                      {t('contracts.col_value')}
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {expiringContracts.map((contract) => (
                    <tr
                      key={contract.id}
                      onClick={() => navigate(`/contracts/${contract.id}`)}
                      className="cursor-pointer border-b border-gray-100 hover:bg-gray-50 transition-colors"
                    >
                      <td className="px-3 py-2 font-medium text-gray-900">{contract.title}</td>
                      <td className="px-3 py-2 text-red-600 font-medium">
                        {contract.end_date || '-'}
                      </td>
                      <td className="px-3 py-2 text-right font-medium text-gray-900">
                        {contract.value != null
                          ? contract.value.toLocaleString(locale, { minimumFractionDigits: 2 })
                          : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* Create Modal */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-2xl">
            <h3 className="mb-4 text-lg font-semibold text-gray-900">
              {t('contracts.modal_create_title')}
            </h3>
            <div className="space-y-3">
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
                  onChange={(e) => setFormCustomerSearch(e.target.value)}
                  placeholder={t('contracts.customer_search_ph')}
                />
                {customerResults?.items &&
                  customerResults.items.length > 0 &&
                  formCustomerSearch.length >= 2 &&
                  !formCustomerId && (
                    <div className="absolute z-20 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg max-h-40 overflow-y-auto">
                      {customerResults.items.map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          onClick={() => {
                            setFormCustomerId(c.id);
                            setFormCustomerSearch(c.company || c.name);
                          }}
                          className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50"
                        >
                          <span className="font-medium">{c.company || c.name}</span>
                          <span className="ml-2 text-xs text-gray-400">{c.email}</span>
                        </button>
                      ))}
                    </div>
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
            <div className="mt-5 flex justify-end gap-2">
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
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
