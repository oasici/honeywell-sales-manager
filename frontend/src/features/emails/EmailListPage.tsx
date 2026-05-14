import { useState, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import {
  Mail,
  User,
  Building2,
  Clock,
  Tag,
  Pencil,
  X,
  Save,
  Package,
  Hash,
  Sparkles,
  RefreshCcw,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { DataTable } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import { emailsApi, customersApi, quotesApi } from '../../lib/api';
import { onCustomerCreated, onEmailChanged } from '../../lib/cacheInvalidation';
import { getErrorMessage } from '../../lib/utils';
import { formatDateTime } from '../../lib/formatters';
import { useT } from '../../hooks/useT';
import {
  EMAIL_CATEGORY_VALUES,
  translateEmailCategory,
  translateReviewStatus,
  translateStatus,
} from '../../lib/labelTranslations';
import type { EmailRequest, PaginatedResponse } from '../../lib/types';

// Map email status / review status → Badge variant. Centralizing here lets
// columns and the detail modal share the same visual language without
// dragging raw class strings around the file.
type BadgeTone = 'success' | 'warning' | 'danger' | 'info' | 'default';
const EMAIL_STATUS_TONE: Record<string, BadgeTone> = {
  received: 'info',
  parsing: 'warning',
  parsed: 'success',
  parse_failed: 'danger',
  processed: 'success',
  ignored: 'default',
};
const REVIEW_TONE: Record<string, BadgeTone> = {
  pending_review: 'warning',
  pending: 'warning',
  approved: 'success',
  rejected: 'danger',
  needs_edit: 'warning',
};

interface ParsedPart {
  part_code?: string;
  part_description?: string;
  quantity?: number;
}

export default function EmailListPage() {
  const t = useT();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [readTab, setReadTab] = useState(searchParams.get('read') || '');
  const [category, setCategory] = useState('');
  const [detailEmail, setDetailEmail] = useState<EmailRequest | null>(null);

  const isReadFilter = readTab === 'read' ? true : readTab === '' ? false : undefined;

  const { data, isLoading } = useQuery<PaginatedResponse<EmailRequest>>({
    queryKey: ['emails', { page, search, is_read: isReadFilter, category }],
    queryFn: () =>
      emailsApi.getEmails({
        page,
        page_size: 20,
        ...(isReadFilter !== undefined && { is_read: isReadFilter }),
        ...(search && { search }),
        ...(category && { category }),
      }),
  });

  const pollMutation = useMutation({
    mutationFn: emailsApi.pollEmails,
    onSuccess: (res) => {
      toast.success(res.message || t('emails.toast_poll_done'));
      onEmailChanged(queryClient, null);
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t('emails.toast_poll_failed')));
    },
  });

  const createCustomerMutation = useMutation({
    mutationFn: (payload: { name: string; email: string; company?: string }) =>
      customersApi.createCustomer(payload),
    onSuccess: (customer) => {
      toast.success(`${t('emails.toast_customer_created_prefix')}: ${customer.name}`);
      // Round-15 Sprint 15g — also invalidates high-intent + dashboard.
      onCustomerCreated(queryClient);
    },
    onError: () => toast.error(t('emails.toast_customer_create_failed')),
  });

  const createQuoteMutation = useMutation({
    mutationFn: (emailId: number) => quotesApi.createQuoteFromEmail(emailId),
    onSuccess: (quote) => {
      toast.success(`${t('emails.toast_draft_quote_created_prefix')}: ${quote.quote_number}`);
      setDetailEmail(null);
      navigate(`/quotes/${quote.id}`);
    },
    onError: () => toast.error(t('emails.toast_quote_create_failed')),
  });

  const reparseMutation = useMutation({
    mutationFn: (emailId: number) => emailsApi.reparseEmail(emailId),
    onSuccess: (res) => {
      toast.success(res.message || t('emails.toast_reparse_done'));
      onEmailChanged(queryClient, detailEmail?.id ?? null);
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t('emails.toast_reparse_failed')));
    },
  });

  const [editingParse, setEditingParse] = useState(false);
  const [editForm, setEditForm] = useState<Record<string, string>>({});

  const correctMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, string> }) =>
      emailsApi.correctParse(id, data),
    onSuccess: (res) => {
      toast.success(res.message);
      setEditingParse(false);
      onEmailChanged(queryClient, detailEmail?.id ?? null);
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t('emails.toast_correction_failed')));
    },
  });

  const reviewMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) =>
      emailsApi.reviewEmail(id, action),
    onSuccess: () => {
      toast.success(t('emails.toast_review_done'));
      onEmailChanged(queryClient, detailEmail?.id ?? null);
      setDetailEmail(null);
    },
    onError: (err: unknown) => {
      toast.error(getErrorMessage(err, t('emails.toast_review_failed')));
    },
  });

  const handleTabChange = useCallback(
    (tab: string) => {
      setReadTab(tab);
      setPage(1);
      if (tab) {
        setSearchParams({ read: tab });
      } else {
        setSearchParams({});
      }
    },
    [setSearchParams],
  );

  // Fetch full email detail when popup opens
  const { data: emailDetail } = useQuery<EmailRequest>({
    queryKey: ['email-detail', detailEmail?.id],
    queryFn: () => emailsApi.getEmail(detailEmail!.id),
    enabled: !!detailEmail?.id,
  });

  // Use fetched detail (has body_text + parsed_data) or fallback to list item
  const activeEmail = emailDetail || detailEmail;

  // Extract parsed data from email
  const getParsedData = (email: EmailRequest | null) => {
    if (!email?.parsed_data) return null;
    try {
      return typeof email.parsed_data === 'string'
        ? JSON.parse(email.parsed_data)
        : email.parsed_data;
    } catch {
      return null;
    }
  };

  // Auto-create customer from parsed email
  const handleCreateCustomer = (email: EmailRequest) => {
    const parsed = getParsedData(email);
    if (!parsed) {
      toast.error(t('emails.toast_not_parsed_yet'));
      return;
    }
    const name = parsed.customer_name || email.from_address.split('@')[0];
    const company = parsed.customer_company || '';
    createCustomerMutation.mutate({
      name,
      email: email.from_address,
      ...(company && { company }),
    });
  };

  const readTabs = [
    { value: '', label: t('emails.list_tab_unread') },
    { value: 'read', label: t('emails.list_tab_read') },
  ];

  const categoryOptions = useMemo(
    () => [
      { value: '', label: t('emails.list_categories_all') },
      ...EMAIL_CATEGORY_VALUES.map((value) => ({
        value,
        label: translateEmailCategory(value, t),
      })),
    ],
    [t],
  );

  const columns = [
    {
      key: 'received_at',
      header: t('emails.list_date'),
      sortable: true,
      render: (row: EmailRequest) => (
        <span className="whitespace-nowrap text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
          {formatDateTime(row.received_at || row.created_at)}
        </span>
      ),
    },
    {
      key: 'from_address',
      header: t('emails.list_sender'),
      render: (row: EmailRequest) => (
        <span className="block max-w-[220px] truncate text-[13px] text-slate-700 dark:text-slate-200">
          {row.from_address}
        </span>
      ),
    },
    {
      key: 'subject',
      header: t('emails.subject'),
      render: (row: EmailRequest) => (
        <span
          className={[
            'block max-w-[280px] truncate text-[13px]',
            row.is_read
              ? 'text-slate-700 dark:text-slate-300'
              : 'font-semibold text-slate-900 dark:text-white',
          ].join(' ')}
        >
          {row.subject || '(Konu yok)'}
        </span>
      ),
    },
    {
      key: 'category',
      header: t('emails.category'),
      render: (row: EmailRequest) =>
        row.category ? (
          <Badge variant="default" size="sm">
            {translateEmailCategory(row.category, t)}
          </Badge>
        ) : (
          <span className="text-[12px] text-slate-400">—</span>
        ),
    },
    {
      key: 'status',
      header: t('common.status'),
      render: (row: EmailRequest) => {
        const tone = EMAIL_STATUS_TONE[row.status] ?? 'default';
        return (
          <Badge variant={tone} size="sm" dot>
            {translateStatus(row.status, t)}
          </Badge>
        );
      },
    },
    {
      key: 'review_status',
      header: t('emails.review'),
      render: (row: EmailRequest) => {
        const rs = row.review_status;
        if (!rs) return <span className="text-[12px] text-slate-400">—</span>;
        const tone = REVIEW_TONE[rs] ?? 'default';
        return (
          <Badge variant={tone} size="sm" dot>
            {translateReviewStatus(rs, t)}
          </Badge>
        );
      },
    },
    {
      key: 'priority',
      header: 'Öncelik',
      // AI-assigned priority — drives default sort + colour. The
      // tooltip below surfaces the model's reason so the user can
      // sanity-check why a message was flagged urgent.
      render: (row: EmailRequest) => {
        const p = row.priority;
        if (!p) return <span className="text-[12px] text-slate-400">—</span>;
        const tone =
          p === 'urgent' ? 'danger' : p === 'high' ? 'warning' : p === 'low' ? 'default' : 'info';
        const label =
          p === 'urgent' ? 'Acil' : p === 'high' ? 'Yüksek' : p === 'low' ? 'Düşük' : 'Normal';
        return (
          <Badge variant={tone} size="sm" title={row.triage_reason ?? undefined}>
            {label}
          </Badge>
        );
      },
    },
    {
      key: 'sentiment',
      header: 'Duygu',
      render: (row: EmailRequest) => {
        const s = row.sentiment;
        if (!s) return <span className="text-[12px] text-slate-400">—</span>;
        const tone = s === 'positive' ? 'success' : s === 'negative' ? 'danger' : 'default';
        const label = s === 'positive' ? 'Olumlu' : s === 'negative' ? 'Olumsuz' : 'Nötr';
        const score = typeof row.sentiment_score === 'number' ? row.sentiment_score : null;
        return (
          <Badge
            variant={tone}
            size="sm"
            title={score != null ? `Skor: ${score.toFixed(2)}` : undefined}
          >
            {label}
          </Badge>
        );
      },
    },
  ];

  const detailParsed = activeEmail ? getParsedData(activeEmail) : null;

  return (
    <div>
      <PageHeader title={t('emails.title')} description={t('emails.description')}>
        <Button loading={pollMutation.isPending} onClick={() => pollMutation.mutate()}>
          <RefreshCcw size={14} />
          {t('emails.list_poll')}
        </Button>
      </PageHeader>

      {/* Filter row — segmented tabs on the left, search + category on the
          right. Wraps to two rows on narrow viewports. */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div
          className="inline-flex flex-wrap gap-1 rounded-[12px] border border-slate-200 bg-slate-50/80 p-1 dark:border-slate-800 dark:bg-slate-900/40"
          role="tablist"
          aria-label={t('emails.list_tab_unread')}
        >
          {readTabs.map((tab) => {
            const isActive = readTab === tab.value;
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

        <div className="ml-auto flex flex-wrap items-end gap-3">
          <div className="w-64">
            <Input
              placeholder={t('emails.list_search_ph')}
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <div className="w-52">
            <Select
              options={categoryOptions}
              value={category}
              onChange={(e) => {
                setCategory(e.target.value);
                setPage(1);
              }}
            />
          </div>
        </div>
      </div>

      {/* Table - rows clickable */}
      <DataTable
        columns={columns}
        data={data?.items || []}
        loading={isLoading}
        emptyMessage={t('emails.list_empty')}
        page={data?.page || page}
        totalPages={data?.pages || 1}
        onPageChange={setPage}
        onRowClick={(row) => {
          const email = row as EmailRequest;
          setDetailEmail(email);
          if (!email.is_read) {
            emailsApi.markRead(email.id).then(() => {
              onEmailChanged(queryClient, null);
            });
          }
        }}
      />

      {/* ── Email Detail Popup ─────────────────────────────────────────
          The popup composes:
            1. Sender + received-at strip (icon medallions)
            2. Subject as the visual anchor
            3. Badges row (category / status / review)
            4. Body in a slate-tinted reading well
            5. AI parse panel (brand-tinted, edit-in-place)
            6. Footer actions (pinned via Modal footer slot)
          ─────────────────────────────────────────────────────────────── */}
      <Modal
        isOpen={!!detailEmail}
        onClose={() => setDetailEmail(null)}
        title={t('emails.detail')}
        size="lg"
        footer={
          activeEmail ? (
            <div className="flex w-full flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="tertiary"
                  size="sm"
                  loading={reparseMutation.isPending}
                  onClick={() => reparseMutation.mutate(activeEmail.id)}
                >
                  <RefreshCcw size={14} />
                  Yeniden Ayrıştır
                </Button>
                {activeEmail.review_status === 'pending_review' && (
                  <>
                    <Button
                      variant="primary"
                      size="sm"
                      loading={reviewMutation.isPending}
                      onClick={() =>
                        reviewMutation.mutate({ id: activeEmail.id, action: 'approve' })
                      }
                    >
                      Onayla
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={reviewMutation.isPending}
                      onClick={() =>
                        reviewMutation.mutate({ id: activeEmail.id, action: 'reject' })
                      }
                    >
                      Reddet
                    </Button>
                  </>
                )}
                {activeEmail.review_status === 'approved' && (
                  <>
                    <Button
                      variant="secondary"
                      size="sm"
                      loading={createCustomerMutation.isPending}
                      onClick={() => handleCreateCustomer(activeEmail)}
                      disabled={!detailParsed}
                    >
                      Müşteri Oluştur
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      loading={createQuoteMutation.isPending}
                      onClick={() => createQuoteMutation.mutate(activeEmail.id)}
                      disabled={!detailParsed?.parts?.length}
                    >
                      Teklif Oluştur
                    </Button>
                  </>
                )}
              </div>
              <Button variant="ghost" size="sm" onClick={() => setDetailEmail(null)}>
                Kapat
              </Button>
            </div>
          ) : null
        }
      >
        {activeEmail && (
          <div className="space-y-5">
            {/* Sender + received-at strip */}
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="flex min-w-0 items-center gap-3">
                <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
                  <Mail size={16} />
                </span>
                <div className="min-w-0">
                  <p className="truncate text-[13px] font-semibold text-slate-900 dark:text-white">
                    {activeEmail.from_address}
                  </p>
                  <span className="text-overline text-slate-400 dark:text-slate-500">
                    {t('emails.list_sender')}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <p className="text-[13px] tabular-nums text-slate-700 dark:text-slate-200">
                    {formatDateTime(activeEmail.received_at || activeEmail.created_at)}
                  </p>
                  <span className="text-overline text-slate-400 dark:text-slate-500">
                    {t('emails.list_date')}
                  </span>
                </div>
                <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
                  <Clock size={16} />
                </span>
              </div>
            </div>

            {/* Subject */}
            <h3 className="text-heading-3 text-slate-900 dark:text-white">
              {activeEmail.subject || '(Konu yok)'}
            </h3>

            {/* Badge row */}
            <div className="flex flex-wrap items-center gap-2">
              {activeEmail.category && (
                <Badge variant="info" size="md">
                  <Tag size={11} />
                  {translateEmailCategory(activeEmail.category, t)}
                </Badge>
              )}
              {activeEmail.status && (
                <Badge variant={EMAIL_STATUS_TONE[activeEmail.status] ?? 'default'} size="md" dot>
                  {translateStatus(activeEmail.status, t)}
                </Badge>
              )}
              {activeEmail.review_status && (
                <Badge variant={REVIEW_TONE[activeEmail.review_status] ?? 'default'} size="md" dot>
                  {translateReviewStatus(activeEmail.review_status, t)}
                </Badge>
              )}
            </div>

            {/* Body reading well */}
            <div className="rounded-2xl border border-slate-200 bg-slate-50/60 p-5 dark:border-slate-800 dark:bg-slate-900/40">
              <span className="text-overline text-slate-500 dark:text-slate-400">
                {t('emails.list_body')}
              </span>
              <div className="mt-3 max-h-48 overflow-y-auto text-[13px] leading-6 text-slate-700 dark:text-slate-300">
                <p className="whitespace-pre-wrap">
                  {(() => {
                    let text = activeEmail.body_text || '';
                    if (!text) return t('emails.no_content');
                    if (text.includes('<')) {
                      text = text
                        .replace(/<(style|script)[^>]*>[\s\S]*?<\/\1>/gi, '')
                        .replace(/<br\s*\/?>/gi, '\n')
                        .replace(/<\/?(p|div|tr|li|h[1-6])[^>]*>/gi, '\n')
                        .replace(/<[^>]+>/g, '');
                    }
                    return text
                      .replace(/&nbsp;/g, ' ')
                      .replace(/&amp;/g, '&')
                      .replace(/&lt;/g, '<')
                      .replace(/&gt;/g, '>')
                      .replace(/&quot;/g, '"')
                      .replace(/&#\d+;/g, '')
                      .replace(/\n\s*\n+/g, '\n\n')
                      .trim();
                  })()}
                </p>
              </div>
            </div>

            {/* AI parse panel — brand-tinted (reads as "AI insight" rather
                than "system info" which is what the previous blue tint
                suggested). Edit toggle flips the panel into a form view. */}
            {detailParsed && (
              <div className="rounded-2xl border border-honeywell-red/15 bg-honeywell-red/4 p-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="inline-flex h-7 w-7 items-center justify-center rounded-[10px] bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                      <Sparkles size={14} />
                    </span>
                    <h4 className="text-overline text-honeywell-red">
                      {t('emails.list_ai_parse_title')}
                    </h4>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      if (!editingParse) {
                        setEditForm({ ...detailParsed });
                      }
                      setEditingParse(!editingParse);
                    }}
                    className="inline-flex h-8 w-8 items-center justify-center rounded-[10px] text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700 focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20"
                    title={editingParse ? t('emails.list_edit_cancel') : t('emails.list_edit')}
                  >
                    {editingParse ? <X size={14} /> : <Pencil size={14} />}
                  </button>
                </div>

                {editingParse ? (
                  <div className="mt-4 space-y-3">
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <Input
                        label="Müşteri"
                        value={editForm.customer_name || ''}
                        onChange={(e) =>
                          setEditForm((f: Record<string, string>) => ({
                            ...f,
                            customer_name: e.target.value,
                          }))
                        }
                      />
                      <Input
                        label="Şirket"
                        value={editForm.customer_company || ''}
                        onChange={(e) =>
                          setEditForm((f: Record<string, string>) => ({
                            ...f,
                            customer_company: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <Input
                      label="Kategori"
                      value={editForm.category || ''}
                      onChange={(e) =>
                        setEditForm((f: Record<string, string>) => ({
                          ...f,
                          category: e.target.value,
                        }))
                      }
                    />
                    <Button
                      variant="primary"
                      size="md"
                      loading={correctMutation.isPending}
                      onClick={() => correctMutation.mutate({ id: activeEmail.id, data: editForm })}
                    >
                      <Save size={14} />
                      Düzeltmeyi Kaydet
                    </Button>
                  </div>
                ) : (
                  <div className="mt-4 space-y-4">
                    {/* Customer / Company facts */}
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {detailParsed.customer_name && (
                        <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
                            <User size={14} />
                          </span>
                          <div className="min-w-0">
                            <span className="block text-overline text-slate-400 dark:text-slate-500">
                              Müşteri
                            </span>
                            <span className="block truncate text-[13px] font-medium text-slate-900 dark:text-white">
                              {detailParsed.customer_name}
                            </span>
                          </div>
                        </div>
                      )}
                      {detailParsed.customer_company && (
                        <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-800 dark:bg-slate-900">
                          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-[10px] bg-slate-50 text-slate-500 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-400 dark:ring-slate-800">
                            <Building2 size={14} />
                          </span>
                          <div className="min-w-0">
                            <span className="block text-overline text-slate-400 dark:text-slate-500">
                              Şirket
                            </span>
                            <span className="block truncate text-[13px] font-medium text-slate-900 dark:text-white">
                              {detailParsed.customer_company}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Parts list */}
                    {detailParsed.parts && detailParsed.parts.length > 0 && (
                      <div>
                        <div className="mb-2 flex items-center gap-2">
                          <Package size={14} className="text-honeywell-red" />
                          <span className="text-overline text-honeywell-red">
                            Talep Edilen Parçalar
                          </span>
                          <Badge variant="default" size="sm">
                            {detailParsed.parts.length}
                          </Badge>
                        </div>
                        <ul className="overflow-hidden rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
                          {detailParsed.parts.map((p: ParsedPart, i: number) => (
                            <li
                              key={i}
                              className="flex items-center justify-between gap-3 border-b border-slate-100 px-3 py-2.5 last:border-b-0 dark:border-slate-800"
                            >
                              <div className="flex min-w-0 items-center gap-3">
                                <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[8px] bg-slate-50 text-slate-400 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:ring-slate-800">
                                  <Hash size={12} />
                                </span>
                                <div className="min-w-0">
                                  <span className="block font-mono text-[13px] font-semibold text-slate-900 dark:text-white">
                                    {p.part_code}
                                  </span>
                                  {p.part_description && (
                                    <span className="block truncate text-[12px] text-slate-500 dark:text-slate-400">
                                      {p.part_description}
                                    </span>
                                  )}
                                </div>
                              </div>
                              <Badge variant="info" size="sm">
                                {p.quantity} adet
                              </Badge>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Confidence bar */}
                    {detailParsed.confidence != null && (
                      <div>
                        <div className="mb-1.5 flex items-center justify-between">
                          <span className="text-overline text-slate-500 dark:text-slate-400">
                            Güven Skoru
                          </span>
                          <span className="text-[13px] font-semibold tabular-nums text-slate-900 dark:text-white">
                            %{Math.round(detailParsed.confidence * 100)}
                          </span>
                        </div>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
                          <div
                            className={[
                              'h-full rounded-full transition-all',
                              detailParsed.confidence >= 0.8
                                ? 'bg-emerald-500'
                                : detailParsed.confidence >= 0.5
                                  ? 'bg-amber-500'
                                  : 'bg-red-500',
                            ].join(' ')}
                            style={{ width: `${Math.round(detailParsed.confidence * 100)}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
