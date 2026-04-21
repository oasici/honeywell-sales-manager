import { useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ReceiptText } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { invoicesApi, customersApi } from '../../lib/api';
import { formatCurrency, currentLocale } from '../../lib/formatters';
import { Modal } from '../../components/ui/Modal';
import { useT } from '../../hooks/useT';
import { translateInvoiceStatus } from '../../lib/labelTranslations';
import type { Invoice, Customer } from '../../lib/types';

const STATUS_VARIANTS: Record<string, 'default' | 'info' | 'warning' | 'success' | 'danger'> = {
  draft: 'default',
  sent: 'info',
  paid: 'success',
  overdue: 'danger',
  voided: 'default',
};

interface CreateForm {
  customer_id: string;
  quote_id: string;
  notes: string;
  tax_rate: string;
  fromQuote: boolean;
}

const INITIAL_FORM: CreateForm = {
  customer_id: '',
  quote_id: '',
  notes: '',
  tax_rate: '18', // Turkey KDV default rate
  fromQuote: false,
};

export default function InvoiceListPage() {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [form, setForm] = useState<CreateForm>(INITIAL_FORM);
  const [customerSearch, setCustomerSearch] = useState('');

  const STATUS_TABS = useMemo(
    () => [
      { value: '', label: t('invoices.status_all') },
      { value: 'draft', label: t('invoices.status_draft') },
      { value: 'sent', label: t('invoices.status_sent') },
      { value: 'paid', label: t('invoices.status_paid') },
      { value: 'overdue', label: t('invoices.status_overdue') },
      { value: 'voided', label: t('invoices.status_voided') },
    ],
    [t],
  );

  const { data, isLoading, isError } = useQuery({
    queryKey: ['invoices', statusFilter],
    queryFn: () => invoicesApi.list(statusFilter ? { status: statusFilter } : {}),
  });

  const invoices: Invoice[] = data?.items ?? [];

  const { data: customerResults } = useQuery<{ items: Customer[] }>({
    queryKey: ['customers-search-invoice', customerSearch],
    queryFn: () => customersApi.getCustomers({ search: customerSearch, page_size: 10 }),
    enabled: customerSearch.length >= 2,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Parameters<typeof invoicesApi.create>[0]) => invoicesApi.create(payload),
    onSuccess: (created: Invoice) => {
      toast.success(t('invoices.toast_created'));
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      setIsCreateOpen(false);
      setForm(INITIAL_FORM);
      navigate(`/invoices/${created.id}`);
    },
    onError: () => toast.error(t('invoices.toast_failed')),
  });

  const createFromQuoteMutation = useMutation({
    mutationFn: (quoteId: number) => invoicesApi.createFromQuote(quoteId),
    onSuccess: (created: Invoice) => {
      toast.success(t('invoices.toast_from_quote'));
      queryClient.invalidateQueries({ queryKey: ['invoices'] });
      setIsCreateOpen(false);
      setForm(INITIAL_FORM);
      navigate(`/invoices/${created.id}`);
    },
    onError: () => toast.error(t('invoices.toast_failed')),
  });

  const handleCreate = useCallback(() => {
    if (form.fromQuote) {
      if (!form.quote_id) {
        toast.error(t('invoices.err_quote_id'));
        return;
      }
      createFromQuoteMutation.mutate(parseInt(form.quote_id));
      return;
    }
    if (!form.customer_id) {
      toast.error(t('invoices.err_customer'));
      return;
    }
    createMutation.mutate({
      customer_id: parseInt(form.customer_id),
      quote_id: form.quote_id ? parseInt(form.quote_id) : undefined,
      notes: form.notes || undefined,
      tax_rate: form.tax_rate ? parseFloat(form.tax_rate) : undefined,
    });
  }, [form, createMutation, createFromQuoteMutation, t]);

  const isPending = createMutation.isPending || createFromQuoteMutation.isPending;

  const locale = currentLocale();

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader title={t('invoices.title')} description={t('invoices.description')} />
        <Card>
          <div className="p-8 text-center">
            <p className="text-sm text-red-500">{t('invoices.load_error')}</p>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title={t('invoices.title')} description={t('invoices.description')}>
        <Button onClick={() => setIsCreateOpen(true)}>
          <ReceiptText className="mr-1.5 h-4 w-4" />
          {t('invoices.new')}
        </Button>
      </PageHeader>

      {/* Status filter tabs */}
      <div className="mb-4 flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            onClick={() => setStatusFilter(tab.value)}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              statusFilter === tab.value
                ? 'bg-honeywell-red text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading && <Skeleton variant="card" count={3} />}

      {!isLoading && invoices.length === 0 && (
        <Card>
          <p className="py-8 text-center text-sm text-gray-500">{t('invoices.empty')}</p>
        </Card>
      )}

      {!isLoading && invoices.length > 0 && (
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-800/50">
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                    {t('invoices.col_number')}
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                    {t('invoices.col_customer')}
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                    {t('invoices.col_status')}
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                    {t('invoices.col_issue')}
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                    {t('invoices.col_due')}
                  </th>
                  <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                    {t('invoices.col_total')}
                  </th>
                </tr>
              </thead>
              <tbody>
                {invoices.map((invoice) => (
                  <tr
                    key={invoice.id}
                    onClick={() => navigate(`/invoices/${invoice.id}`)}
                    className="cursor-pointer border-b border-gray-100 hover:bg-gray-50 transition-colors dark:border-gray-700 dark:hover:bg-gray-800/40"
                  >
                    <td className="px-3 py-2 font-mono font-medium text-gray-900 dark:text-white">
                      {invoice.invoice_number}
                    </td>
                    <td className="px-3 py-2 text-gray-700 dark:text-gray-300">
                      <span className="font-medium">
                        {invoice.customer?.name ?? `#${invoice.customer_id}`}
                      </span>
                      {invoice.customer?.company && (
                        <span className="ml-1.5 text-xs text-gray-400">
                          {invoice.customer.company}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2">
                      <Badge variant={STATUS_VARIANTS[invoice.status] ?? 'default'}>
                        {translateInvoiceStatus(invoice.status, t)}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-gray-600 dark:text-gray-400">
                      {invoice.issue_date
                        ? new Date(invoice.issue_date).toLocaleDateString(locale)
                        : '-'}
                    </td>
                    <td className="px-3 py-2 text-gray-600 dark:text-gray-400">
                      {invoice.due_date
                        ? new Date(invoice.due_date).toLocaleDateString(locale)
                        : '-'}
                    </td>
                    <td className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-white">
                      {formatCurrency(invoice.grand_total, invoice.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Create Invoice Modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => {
          setIsCreateOpen(false);
          setForm(INITIAL_FORM);
          setCustomerSearch('');
        }}
        title={t('invoices.modal_new')}
      >
        {/* Mode toggle */}
        <div className="mb-4 flex gap-2">
          <button
            type="button"
            onClick={() => setForm({ ...form, fromQuote: false })}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              !form.fromQuote
                ? 'bg-honeywell-red text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300'
            }`}
          >
            {t('invoices.mode_manual')}
          </button>
          <button
            type="button"
            onClick={() => setForm({ ...form, fromQuote: true })}
            className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
              form.fromQuote
                ? 'bg-honeywell-red text-white'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300'
            }`}
          >
            {t('invoices.mode_from_quote')}
          </button>
        </div>

        <div className="space-y-3">
          {form.fromQuote ? (
            <Input
              label={t('invoices.quote_id')}
              type="number"
              value={form.quote_id}
              onChange={(e) => setForm({ ...form, quote_id: e.target.value })}
              placeholder={t('invoices.quote_id_ph')}
            />
          ) : (
            <>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('invoices.search_customer')}
                </label>
                <input
                  type="text"
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                  placeholder={t('invoices.search_customer_ph')}
                  value={customerSearch}
                  onChange={(e) => setCustomerSearch(e.target.value)}
                />
                {customerSearch.length >= 2 && (
                  <div className="mt-1 max-h-40 overflow-y-auto rounded-lg border border-gray-200 bg-white dark:border-gray-600 dark:bg-gray-800">
                    {!customerResults?.items?.length && (
                      <p className="px-3 py-2 text-sm text-gray-400">{t('invoices.no_customer')}</p>
                    )}
                    {customerResults?.items?.map((c) => (
                      <button
                        key={c.id}
                        type="button"
                        onClick={() => {
                          setForm({ ...form, customer_id: String(c.id) });
                          setCustomerSearch(`${c.name} — ${c.company}`);
                        }}
                        className="w-full px-3 py-2 text-left text-sm hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                      >
                        <span className="font-medium text-gray-900 dark:text-white">{c.name}</span>
                        <span className="ml-2 text-xs text-gray-400">{c.company}</span>
                      </button>
                    ))}
                  </div>
                )}
                {form.customer_id && (
                  <p className="mt-1 text-xs text-green-600">
                    {t('invoices.selected_id')}: {form.customer_id}
                  </p>
                )}
              </div>
              <Input
                label={t('invoices.quote_optional')}
                type="number"
                value={form.quote_id}
                onChange={(e) => setForm({ ...form, quote_id: e.target.value })}
                placeholder={t('invoices.quote_optional_ph')}
              />
              <Input
                label={t('invoices.tax_rate')}
                type="number"
                min={0}
                max={100}
                step={1}
                value={form.tax_rate}
                onChange={(e) => setForm({ ...form, tax_rate: e.target.value })}
              />
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
                  {t('invoices.notes')}
                </label>
                <textarea
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm placeholder:text-gray-400 focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                  rows={2}
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  placeholder={t('invoices.notes_ph')}
                />
              </div>
            </>
          )}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <Button
            variant="secondary"
            onClick={() => {
              setIsCreateOpen(false);
              setForm(INITIAL_FORM);
              setCustomerSearch('');
            }}
          >
            {t('common.cancel')}
          </Button>
          <Button onClick={handleCreate} loading={isPending}>
            {t('common.create')}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
