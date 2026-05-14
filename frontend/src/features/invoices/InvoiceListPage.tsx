import { useState, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ReceiptText, Coins, FileWarning, Wallet } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { invoicesApi, customersApi } from '../../lib/api';
import { onInvoiceCreated } from '../../lib/cacheInvalidation';
import { formatCurrency, formatDate } from '../../lib/formatters';
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

/**
 * KpiTile — small card used in the page summary strip.
 *
 * Layout: icon medallion + overline label on top, large tabular-nums value
 * below. `tone` shifts the value color (positive=emerald, negative=red).
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
      // Round-15 Sprint 15g cohort 6 — also invalidates rev-rec +
      // cockpit + dashboard + customer-360 via the helper.
      onInvoiceCreated(queryClient, created.customer_id);
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
      onInvoiceCreated(queryClient, created.customer_id);
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

  if (isError) {
    return (
      <div>
        <PageHeader title={t('invoices.title')} description={t('invoices.description')} />
        <div className="rounded-2xl border border-red-100 bg-red-50/40 p-8 text-center dark:border-red-900/40 dark:bg-red-950/20">
          <p className="text-[14px] font-medium text-red-700 dark:text-red-400">
            {t('invoices.load_error')}
          </p>
        </div>
      </div>
    );
  }

  // KPI summary derived from the currently filtered list. Uses the
  // canonical TRY currency for the strip totals; per-row totals keep
  // their original currency.
  const summary = useMemo(() => {
    const total = invoices.length;
    let unpaid = 0;
    let overdue = 0;
    let collectedThisMonth = 0;
    const startOfMonth = new Date();
    startOfMonth.setDate(1);
    startOfMonth.setHours(0, 0, 0, 0);
    for (const inv of invoices) {
      if (inv.status === 'paid') {
        const paidAt = inv.paid_at ? new Date(inv.paid_at) : null;
        if (paidAt && paidAt >= startOfMonth) {
          collectedThisMonth += inv.grand_total;
        }
      } else if (inv.status === 'overdue') {
        overdue += inv.grand_total;
        unpaid += inv.grand_total;
      } else if (inv.status === 'sent' || inv.status === 'draft') {
        unpaid += inv.grand_total;
      }
    }
    return { total, unpaid, overdue, collectedThisMonth };
  }, [invoices]);

  return (
    <div>
      <PageHeader title={t('invoices.title')} description={t('invoices.description')}>
        <Button onClick={() => setIsCreateOpen(true)}>
          <ReceiptText size={14} />
          {t('invoices.new')}
        </Button>
      </PageHeader>

      {/* KPI summary strip — anchors the page with the four numbers a
          finance lead reaches for first. Tabular-nums keeps the values
          aligned across cards even at large amounts. */}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiTile
          icon={<ReceiptText size={14} />}
          label="Toplam Fatura"
          value={String(summary.total)}
        />
        <KpiTile
          icon={<Coins size={14} />}
          label="Ödenmemiş Tutar"
          value={formatCurrency(summary.unpaid, 'TRY')}
        />
        <KpiTile
          icon={<FileWarning size={14} />}
          label="Geciken Fatura"
          value={formatCurrency(summary.overdue, 'TRY')}
          tone={summary.overdue > 0 ? 'negative' : 'default'}
        />
        <KpiTile
          icon={<Wallet size={14} />}
          label="Bu Ay Tahsilat"
          value={formatCurrency(summary.collectedThisMonth, 'TRY')}
          tone="positive"
        />
      </div>

      {/* Status segmented tabs (matches QuoteListPage / EmailListPage) */}
      <div
        className="mb-4 inline-flex flex-wrap gap-1 rounded-[12px] border border-slate-200 bg-slate-50/80 p-1 dark:border-slate-800 dark:bg-slate-900/40"
        role="tablist"
        aria-label={t('invoices.col_status')}
      >
        {STATUS_TABS.map((tab) => {
          const isActive = statusFilter === tab.value;
          return (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => setStatusFilter(tab.value)}
              className={[
                'inline-flex h-8 items-center rounded-[10px] px-3 text-[13px] font-medium transition-all',
                'focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20',
                isActive
                  ? 'bg-white text-slate-900 shadow-(--shadow-xs) dark:bg-slate-800 dark:text-white'
                  : 'text-slate-600 hover:bg-white/60 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200',
              ].join(' ')}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {isLoading && <Skeleton variant="table" />}

      {!isLoading && invoices.length === 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white py-2 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <EmptyState
            variant="default"
            icon={<ReceiptText size={20} />}
            title={t('invoices.empty')}
            action={
              <Button onClick={() => setIsCreateOpen(true)} variant="secondary">
                <ReceiptText size={14} />
                {t('invoices.new')}
              </Button>
            }
          />
        </div>
      )}

      {!isLoading && invoices.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50/60 dark:border-slate-800 dark:bg-slate-900/40">
                  <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                    {t('invoices.col_number')}
                  </th>
                  <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                    {t('invoices.col_customer')}
                  </th>
                  <th className="px-4 py-3 text-overline text-slate-500 dark:text-slate-400">
                    {t('invoices.col_status')}
                  </th>
                  {/* R6-RESP-1 — issue/due dates collapse on mobile so the
                      sub-400px viewport doesn't sideways-scroll the table. */}
                  <th className="hidden px-4 py-3 text-overline text-slate-500 sm:table-cell dark:text-slate-400">
                    {t('invoices.col_issue')}
                  </th>
                  <th className="hidden px-4 py-3 text-overline text-slate-500 sm:table-cell dark:text-slate-400">
                    {t('invoices.col_due')}
                  </th>
                  <th className="px-4 py-3 text-right text-overline text-slate-500 dark:text-slate-400">
                    {t('invoices.col_total')}
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {invoices.map((invoice) => (
                  <tr
                    key={invoice.id}
                    onClick={() => navigate(`/invoices/${invoice.id}`)}
                    className="cursor-pointer transition-colors hover:bg-slate-50 dark:hover:bg-slate-800/40"
                  >
                    <td className="whitespace-nowrap px-4 py-3 font-mono text-[13px] font-semibold text-slate-900 dark:text-white">
                      {invoice.invoice_number}
                    </td>
                    <td className="px-4 py-3">
                      <div className="min-w-0">
                        <p className="truncate text-[13px] font-medium text-slate-900 dark:text-white">
                          {invoice.customer?.name ?? `#${invoice.customer_id}`}
                        </p>
                        {invoice.customer?.company && (
                          <p className="truncate text-[12px] text-slate-500 dark:text-slate-400">
                            {invoice.customer.company}
                          </p>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={STATUS_VARIANTS[invoice.status] ?? 'default'} size="sm" dot>
                        {translateInvoiceStatus(invoice.status, t)}
                      </Badge>
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-3 text-[12px] tabular-nums text-slate-500 sm:table-cell dark:text-slate-400">
                      {invoice.issue_date ? formatDate(invoice.issue_date) : '—'}
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-3 text-[12px] tabular-nums text-slate-500 sm:table-cell dark:text-slate-400">
                      {invoice.due_date ? formatDate(invoice.due_date) : '—'}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right text-[13px] font-semibold tabular-nums text-slate-900 dark:text-white">
                      {formatCurrency(invoice.grand_total, invoice.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Create Invoice Modal — uses Modal's footer slot. */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => {
          setIsCreateOpen(false);
          setForm(INITIAL_FORM);
          setCustomerSearch('');
        }}
        title={t('invoices.modal_new')}
        size="md"
        footer={
          <>
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
          </>
        }
      >
        {/* Mode toggle — segmented control matching the page status tabs */}
        <div
          className="mb-4 inline-flex gap-1 rounded-[12px] border border-slate-200 bg-slate-50/80 p-1 dark:border-slate-800 dark:bg-slate-900/40"
          role="tablist"
          aria-label="Fatura oluşturma modu"
        >
          {[
            { value: false, label: t('invoices.mode_manual') },
            { value: true, label: t('invoices.mode_from_quote') },
          ].map((opt) => {
            const isActive = form.fromQuote === opt.value;
            return (
              <button
                key={String(opt.value)}
                type="button"
                role="tab"
                aria-selected={isActive}
                onClick={() => setForm({ ...form, fromQuote: opt.value })}
                className={[
                  'inline-flex h-8 items-center rounded-[10px] px-3 text-[13px] font-medium transition-all',
                  'focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20',
                  isActive
                    ? 'bg-white text-slate-900 shadow-(--shadow-xs) dark:bg-slate-800 dark:text-white'
                    : 'text-slate-600 hover:bg-white/60 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200',
                ].join(' ')}
              >
                {opt.label}
              </button>
            );
          })}
        </div>

        <div className="space-y-4">
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
              <Input
                label={t('invoices.search_customer')}
                placeholder={t('invoices.search_customer_ph')}
                value={customerSearch}
                onChange={(e) => setCustomerSearch(e.target.value)}
              />
              {customerSearch.length >= 2 && (
                <div className="overflow-hidden rounded-[12px] border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
                  {!customerResults?.items?.length ? (
                    <p className="px-3 py-2.5 text-[13px] text-slate-400">
                      {t('invoices.no_customer')}
                    </p>
                  ) : (
                    <ul className="max-h-44 divide-y divide-slate-100 overflow-y-auto dark:divide-slate-700">
                      {customerResults.items.map((c) => (
                        <li key={c.id}>
                          <button
                            type="button"
                            onClick={() => {
                              setForm({ ...form, customer_id: String(c.id) });
                              setCustomerSearch(`${c.name}${c.company ? ` — ${c.company}` : ''}`);
                            }}
                            className="flex w-full items-baseline gap-2 px-3 py-2.5 text-left transition-colors hover:bg-slate-50 dark:hover:bg-slate-700/60"
                          >
                            <span className="text-[13px] font-medium text-slate-900 dark:text-white">
                              {c.name}
                            </span>
                            {c.company && (
                              <span className="text-[12px] text-slate-500 dark:text-slate-400">
                                {c.company}
                              </span>
                            )}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              {form.customer_id && (
                <p className="text-[12px] font-medium text-emerald-600 dark:text-emerald-400">
                  {t('invoices.selected_id')}: {form.customer_id}
                </p>
              )}
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
                <label className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300">
                  {t('invoices.notes')}
                </label>
                <textarea
                  className="block w-full resize-none rounded-[12px] border border-slate-200 bg-white px-3.5 py-2.5 text-[13px] text-slate-900 placeholder:text-slate-400 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-transparent dark:text-slate-100 dark:placeholder:text-slate-500"
                  rows={3}
                  value={form.notes}
                  onChange={(e) => setForm({ ...form, notes: e.target.value })}
                  placeholder={t('invoices.notes_ph')}
                />
              </div>
            </>
          )}
        </div>
      </Modal>
    </div>
  );
}
