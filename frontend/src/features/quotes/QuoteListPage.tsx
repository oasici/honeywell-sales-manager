import { useState, useRef, useMemo } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { quotesApi } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/formatters';
import { STATUS_COLORS } from '../../lib/constants';
import type { TranslationKey } from '../../lib/i18n';
import type { Quote, PaginatedResponse } from '../../lib/types';
import { useT } from '../../hooks/useT';

const QUOTE_STATUS_KEYS: Record<string, TranslationKey> = {
  draft: 'sales_analytics.stage_draft',
  pending_approval: 'sales_analytics.stage_pending',
  approved: 'sales_analytics.stage_approved',
  sent: 'sales_analytics.stage_sent',
  accepted: 'quotes.list_status_accepted',
  rejected: 'sales_analytics.stage_rejected',
  expired: 'sales_analytics.stage_expired',
  cancelled: 'quotes.list_status_cancelled',
};

export default function QuoteListPage() {
  const t = useT();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [statusTab, setStatusTab] = useState(searchParams.get('status') || '');

  const statusTabs = useMemo(
    () => [
      { value: '', label: t('quotes.list_tab_all') },
      { value: 'draft', label: t('quotes.list_tab_draft') },
      { value: 'pending_approval', label: t('quotes.list_tab_pending') },
      { value: 'approved', label: t('quotes.list_tab_approved') },
      { value: 'sent', label: t('quotes.list_tab_sent') },
    ],
    [t],
  );

  const { data, isLoading } = useQuery<PaginatedResponse<Quote>>({
    queryKey: ['quotes', { page, status: statusTab }],
    queryFn: () =>
      quotesApi.getQuotes({
        page,
        page_size: 20,
        ...(statusTab && { status: statusTab }),
      }),
  });

  const handleTabChange = (tab: string) => {
    setStatusTab(tab);
    setPage(1);
    if (tab) {
      setSearchParams({ status: tab });
    } else {
      setSearchParams({});
    }
  };

  const pdfRef = useRef<HTMLInputElement>(null);

  const pdfMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      const { data: result } = await (
        await import('../../lib/api')
      ).default.post('/quotes/from-pdf', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return result;
    },
    onSuccess: (quote: Quote) => {
      toast.success(t('quotes.toast_pdf_created').replace('{number}', quote.quote_number));
      navigate(`/quotes/${quote.id}`);
    },
    onError: (err: unknown) => {
      const msg =
        (err as { response?: { data?: { error?: { message?: string } } } })?.response?.data?.error
          ?.message || t('quotes.err_pdf_import');
      toast.error(msg);
    },
  });

  const handlePdfImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      pdfMutation.mutate(file);
      e.target.value = '';
    }
  };

  const columns = useMemo(
    () => [
      {
        key: 'quote_number',
        header: t('quotes.list_col_number'),
        sortable: true,
        render: (row: Quote) => (
          <button
            type="button"
            onClick={() => navigate(`/quotes/${row.id}`)}
            className="font-semibold text-honeywell-red hover:underline"
          >
            {row.quote_number}
          </button>
        ),
      },
      {
        key: 'customer',
        header: t('quotes.list_col_customer'),
        render: (row: Quote) => (
          <span className="text-sm">{row.customer?.company || row.customer?.name || '-'}</span>
        ),
      },
      {
        key: 'status',
        header: t('quotes.list_col_status'),
        render: (row: Quote) => {
          const key = QUOTE_STATUS_KEYS[row.status];
          const label = key ? t(key) : row.status;
          return (
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                STATUS_COLORS[row.status] || 'bg-gray-100 text-gray-700'
              }`}
            >
              {label}
            </span>
          );
        },
      },
      {
        key: 'grand_total',
        header: t('quotes.list_col_total'),
        sortable: true,
        render: (row: Quote) => (
          <span className="font-medium text-sm">
            {formatCurrency(row.grand_total, row.currency)}
          </span>
        ),
      },
      {
        key: 'currency',
        header: t('quotes.list_col_currency'),
        render: (row: Quote) => <span className="text-sm">{row.currency}</span>,
      },
      {
        key: 'created_at',
        header: t('quotes.list_col_date'),
        sortable: true,
        render: (row: Quote) => (
          <span className="text-sm whitespace-nowrap">{formatDate(row.created_at)}</span>
        ),
      },
    ],
    [t, navigate],
  );

  return (
    <div>
      <PageHeader title={t('quotes.title')} description={t('quotes.description')}>
        <input
          type="file"
          ref={pdfRef}
          accept=".pdf"
          className="hidden"
          onChange={handlePdfImport}
        />
        <Button
          variant="secondary"
          loading={pdfMutation.isPending}
          onClick={() => pdfRef.current?.click()}
        >
          {t('quotes.list_pdf_import')}
        </Button>
        <Button onClick={() => navigate('/quotes/new')}>{t('quotes.list_new')}</Button>
      </PageHeader>

      {/* Status Tabs */}
      <div className="mb-4 flex flex-wrap gap-1 rounded-lg bg-gray-100 p-1">
        {statusTabs.map((tab) => (
          <button
            key={tab.value}
            type="button"
            onClick={() => handleTabChange(tab.value)}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              statusTab === tab.value
                ? 'bg-white text-honeywell-red shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Table */}
      <DataTable
        columns={columns}
        data={data?.items || []}
        loading={isLoading}
        emptyMessage={t('quotes.list_empty')}
        page={data?.page || page}
        totalPages={data?.pages || 1}
        onPageChange={setPage}
      />
    </div>
  );
}
