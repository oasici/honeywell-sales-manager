import { useState, useRef, useMemo } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { FileUp, Plus } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Badge } from '../../components/ui/Badge';
import { quotesApi } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/formatters';
import type { TranslationKey } from '../../lib/i18n';
import type { Quote, PaginatedResponse } from '../../lib/types';
import { useT } from '../../hooks/useT';

// Map quote status → Badge variant. Keeps the visual language consistent
// with the rest of the design system instead of pulling raw class strings.
type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'default';
const QUOTE_STATUS_TONE: Record<string, BadgeTone> = {
  draft: 'default',
  pending_approval: 'warning',
  approved: 'success',
  sent: 'info',
  accepted: 'success',
  rejected: 'danger',
  expired: 'warning',
  cancelled: 'default',
};

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

  const { data, isLoading, isError, error, refetch } = useQuery<PaginatedResponse<Quote>>({
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
            className="text-[13px] font-semibold tabular-nums text-slate-900 transition-colors hover:text-honeywell-red dark:text-white"
          >
            {row.quote_number}
          </button>
        ),
      },
      {
        key: 'customer',
        header: t('quotes.list_col_customer'),
        render: (row: Quote) => (
          <span className="text-[13px] text-slate-700 dark:text-slate-200">
            {row.customer?.company || row.customer?.name || '—'}
          </span>
        ),
      },
      {
        key: 'status',
        header: t('quotes.list_col_status'),
        render: (row: Quote) => {
          const key = QUOTE_STATUS_KEYS[row.status];
          const label = key ? t(key) : row.status;
          const tone = QUOTE_STATUS_TONE[row.status] ?? 'default';
          return (
            <Badge variant={tone} size="sm" dot>
              {label}
            </Badge>
          );
        },
      },
      {
        key: 'grand_total',
        header: t('quotes.list_col_total'),
        sortable: true,
        align: 'right' as const,
        numeric: true,
        render: (row: Quote) => (
          <span className="text-[13px] font-semibold tabular-nums text-slate-900 dark:text-white">
            {formatCurrency(row.grand_total, row.currency)}
          </span>
        ),
      },
      {
        key: 'currency',
        header: t('quotes.list_col_currency'),
        width: '80px',
        render: (row: Quote) => (
          <span className="text-[12px] font-medium uppercase tracking-wider text-slate-500 dark:text-slate-400">
            {row.currency}
          </span>
        ),
      },
      {
        key: 'created_at',
        header: t('quotes.list_col_date'),
        sortable: true,
        render: (row: Quote) => (
          <span className="whitespace-nowrap text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
            {formatDate(row.created_at)}
          </span>
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
          <FileUp size={14} />
          {t('quotes.list_pdf_import')}
        </Button>
        <Button onClick={() => navigate('/quotes/new')}>
          <Plus size={14} />
          {t('quotes.list_new')}
        </Button>
      </PageHeader>

      {/* Status segmented tabs — sit on a slate-50 well; active pill uses
          surface white + brand label so the selection state is unambiguous
          even at a glance. Border-bottom on the well separates tabs from the
          table without an extra horizontal rule. */}
      <div
        className="mb-4 inline-flex flex-wrap gap-1 rounded-[12px] border border-slate-200 bg-slate-50/80 p-1 dark:border-slate-800 dark:bg-slate-900/40"
        role="tablist"
        aria-label={t('quotes.list_tab_all')}
      >
        {statusTabs.map((tab) => {
          const isActive = statusTab === tab.value;
          return (
            <button
              key={tab.value}
              type="button"
              role="tab"
              aria-selected={isActive}
              onClick={() => handleTabChange(tab.value)}
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

      {/* Round-11 R11-FE-1 — surface load failure instead of silently
          returning an empty table. */}
      {isError && (
        <div className="mb-3 flex items-center justify-between rounded-[8px] border border-(--danger)/30 bg-(--danger-bg) px-3 py-2 text-[13px] text-(--danger)">
          <span>
            {(error as Error | undefined)?.message ?? t('common.error_load_failed')}
          </span>
          <Button variant="ghost" onClick={() => refetch()}>
            {t('common.retry')}
          </Button>
        </div>
      )}

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
