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
  BarChart3,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { DataTable } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
import { emailsApi, customersApi, quotesApi } from '../../lib/api';
import { getErrorMessage } from '../../lib/utils';
import { formatDateTime } from '../../lib/formatters';
import { useT } from '../../hooks/useT';
import { REVIEW_STATUS_COLORS, STATUS_COLORS } from '../../lib/constants';
import {
  EMAIL_CATEGORY_VALUES,
  translateEmailCategory,
  translateReviewStatus,
  translateStatus,
} from '../../lib/labelTranslations';
import type { EmailRequest, PaginatedResponse } from '../../lib/types';

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
      queryClient.invalidateQueries({ queryKey: ['emails'] });
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
      queryClient.invalidateQueries({ queryKey: ['customers'] });
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
      queryClient.invalidateQueries({ queryKey: ['emails'] });
      if (detailEmail) {
        queryClient.invalidateQueries({ queryKey: ['email-detail', detailEmail.id] });
      }
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
      queryClient.invalidateQueries({ queryKey: ['emails'] });
      if (detailEmail) {
        queryClient.invalidateQueries({ queryKey: ['email-detail', detailEmail.id] });
      }
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
      queryClient.invalidateQueries({ queryKey: ['emails'] });
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
        <span className="whitespace-nowrap text-sm">
          {formatDateTime(row.received_at || row.created_at)}
        </span>
      ),
    },
    {
      key: 'from_address',
      header: t('emails.list_sender'),
      render: (row: EmailRequest) => (
        <span className="max-w-[200px] truncate block text-sm">{row.from_address}</span>
      ),
    },
    {
      key: 'subject',
      header: t('emails.subject'),
      render: (row: EmailRequest) => (
        <span className="max-w-[260px] truncate block text-sm font-medium text-honeywell-red">
          {row.subject || '(Konu yok)'}
        </span>
      ),
    },
    {
      key: 'category',
      header: t('emails.category'),
      render: (row: EmailRequest) => (
        <span className="text-sm">
          {row.category ? translateEmailCategory(row.category, t) : '-'}
        </span>
      ),
    },
    {
      key: 'status',
      header: t('common.status'),
      render: (row: EmailRequest) => (
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
            STATUS_COLORS[row.status] || 'bg-gray-100 text-gray-700'
          }`}
        >
          {translateStatus(row.status, t)}
        </span>
      ),
    },
    {
      key: 'review_status',
      header: t('emails.review'),
      render: (row: EmailRequest) => {
        const rs = row.review_status;
        if (!rs) return <span className="text-gray-400 text-sm">-</span>;
        return (
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
              REVIEW_STATUS_COLORS[rs] || 'bg-gray-100 text-gray-700'
            }`}
          >
            {translateReviewStatus(rs, t)}
          </span>
        );
      },
    },
  ];

  const detailParsed = activeEmail ? getParsedData(activeEmail) : null;

  return (
    <div>
      <PageHeader title={t('emails.title')} description={t('emails.description')}>
        <Button loading={pollMutation.isPending} onClick={() => pollMutation.mutate()}>
          {t('emails.list_poll')}
        </Button>
      </PageHeader>

      {/* Tabs */}
      <div className="mb-4 flex flex-wrap gap-1 rounded-lg bg-gray-100 p-1">
        {readTabs.map((tab) => (
          <button
            key={tab.value}
            type="button"
            onClick={() => handleTabChange(tab.value)}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              readTab === tab.value
                ? 'bg-white text-honeywell-red shadow-sm'
                : 'text-gray-600 hover:text-gray-900'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-4">
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
        <div className="w-48">
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
              queryClient.invalidateQueries({ queryKey: ['emails'] });
            });
          }
        }}
      />

      {/* ── Email Detail Popup ── */}
      <Modal
        isOpen={!!detailEmail}
        onClose={() => setDetailEmail(null)}
        title={t('emails.detail')}
        size="lg"
      >
        {activeEmail && (
          <div className="space-y-5">
            {/* Header: Sender + Date side by side */}
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100">
                  <Mail size={16} className="text-slate-500" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-gray-900">{activeEmail.from_address}</p>
                  <span className="text-xs text-gray-400">{t('emails.list_sender')}</span>
                </div>
              </div>
              <div className="flex items-center gap-2 text-right">
                <div>
                  <p className="text-sm text-gray-700">
                    {formatDateTime(activeEmail.received_at || activeEmail.created_at)}
                  </p>
                  <span className="text-xs text-gray-400">{t('emails.list_date')}</span>
                </div>
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100">
                  <Clock size={16} className="text-slate-500" />
                </div>
              </div>
            </div>

            {/* Subject bold below */}
            <div>
              <p className="text-base font-bold text-gray-900 leading-snug">
                {activeEmail.subject || '(Konu yok)'}
              </p>
            </div>

            {/* Status badges - pill shaped, vibrant */}
            <div className="flex flex-wrap items-center gap-2">
              {activeEmail.category && (
                <span className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-3 py-1 text-xs font-semibold text-indigo-700">
                  <Tag size={12} />
                  {translateEmailCategory(activeEmail.category, t)}
                </span>
              )}
              {activeEmail.status && (
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${
                    activeEmail.status === 'parsed'
                      ? 'bg-emerald-100 text-emerald-700'
                      : 'bg-gray-100 text-gray-600'
                  }`}
                >
                  {translateStatus(activeEmail.status, t)}
                </span>
              )}
              {activeEmail.review_status && (
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ${
                    activeEmail.review_status === 'approved'
                      ? 'bg-emerald-100 text-emerald-700'
                      : activeEmail.review_status === 'rejected'
                        ? 'bg-rose-100 text-rose-700'
                        : 'bg-amber-100 text-amber-700'
                  }`}
                >
                  {translateReviewStatus(activeEmail.review_status, t)}
                </span>
              )}
            </div>

            {/* Email body */}
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-5">
              <span className="mb-3 block text-xs font-semibold uppercase tracking-wider text-slate-400">
                {t('emails.list_body')}
              </span>
              <div className="max-h-48 overflow-y-auto text-sm leading-relaxed text-gray-700">
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

            {/* AI Parse Results - card-within-card */}
            {detailParsed && (
              <div className="rounded-xl border border-blue-200 bg-blue-50/60 p-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <BarChart3 size={16} className="text-blue-600" />
                    <h4 className="text-xs font-bold uppercase tracking-wider text-blue-700">
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
                    className="flex h-8 w-8 items-center justify-center rounded-lg text-blue-500 transition-colors hover:bg-blue-100 hover:text-blue-700"
                    title={editingParse ? t('emails.list_edit_cancel') : t('emails.list_edit')}
                  >
                    {editingParse ? <X size={16} /> : <Pencil size={14} />}
                  </button>
                </div>

                {editingParse ? (
                  <div className="mt-4 space-y-4">
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      <div>
                        <label className="mb-1.5 block text-xs font-semibold text-blue-700">
                          Müşteri
                        </label>
                        <input
                          className="w-full rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm shadow-sm outline-none transition-colors focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                          value={editForm.customer_name || ''}
                          onChange={(e) =>
                            setEditForm((f: Record<string, string>) => ({
                              ...f,
                              customer_name: e.target.value,
                            }))
                          }
                        />
                      </div>
                      <div>
                        <label className="mb-1.5 block text-xs font-semibold text-blue-700">
                          Şirket
                        </label>
                        <input
                          className="w-full rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm shadow-sm outline-none transition-colors focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                          value={editForm.customer_company || ''}
                          onChange={(e) =>
                            setEditForm((f: Record<string, string>) => ({
                              ...f,
                              customer_company: e.target.value,
                            }))
                          }
                        />
                      </div>
                    </div>
                    <div>
                      <label className="mb-1.5 block text-xs font-semibold text-blue-700">
                        Kategori
                      </label>
                      <input
                        className="w-full rounded-lg border border-blue-200 bg-white px-3 py-2 text-sm shadow-sm outline-none transition-colors focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                        value={editForm.category || ''}
                        onChange={(e) =>
                          setEditForm((f: Record<string, string>) => ({
                            ...f,
                            category: e.target.value,
                          }))
                        }
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        correctMutation.mutate({ id: activeEmail!.id, data: editForm })
                      }
                      disabled={correctMutation.isPending}
                      className="inline-flex items-center gap-2 rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-blue-700 disabled:opacity-50"
                    >
                      <Save size={14} />
                      {correctMutation.isPending ? 'Kaydediliyor...' : 'Duzeltmeyi Kaydet'}
                    </button>
                  </div>
                ) : (
                  <div className="mt-4 space-y-4">
                    {/* Customer / Company 2-col grid with icons */}
                    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                      {detailParsed.customer_name && (
                        <div className="flex items-center gap-3 rounded-lg bg-white p-3 shadow-sm">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100">
                            <User size={14} className="text-blue-600" />
                          </div>
                          <div>
                            <span className="block text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                              Müşteri
                            </span>
                            <span className="text-sm font-medium text-gray-900">
                              {detailParsed.customer_name}
                            </span>
                          </div>
                        </div>
                      )}
                      {detailParsed.customer_company && (
                        <div className="flex items-center gap-3 rounded-lg bg-white p-3 shadow-sm">
                          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-100">
                            <Building2 size={14} className="text-blue-600" />
                          </div>
                          <div>
                            <span className="block text-[10px] font-semibold uppercase tracking-wider text-gray-400">
                              Şirket
                            </span>
                            <span className="text-sm font-medium text-gray-900">
                              {detailParsed.customer_company}
                            </span>
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Parts list - mini cards */}
                    {detailParsed.parts && detailParsed.parts.length > 0 && (
                      <div>
                        <div className="mb-2 flex items-center gap-2">
                          <Package size={14} className="text-blue-600" />
                          <span className="text-xs font-bold uppercase tracking-wider text-blue-700">
                            Talep Edilen Parçalar
                          </span>
                          <span className="inline-flex h-5 min-w-[20px] items-center justify-center rounded-full bg-blue-200 px-1.5 text-[10px] font-bold text-blue-800">
                            {detailParsed.parts.length}
                          </span>
                        </div>
                        <div className="space-y-2">
                          {detailParsed.parts.map((p: ParsedPart, i: number) => (
                            <div
                              key={i}
                              className="flex items-center justify-between rounded-lg bg-white p-3 shadow-sm"
                            >
                              <div className="flex items-center gap-3">
                                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-slate-100">
                                  <Hash size={12} className="text-slate-500" />
                                </div>
                                <div>
                                  <span className="block font-mono text-sm font-bold text-gray-900">
                                    {p.part_code}
                                  </span>
                                  {p.part_description && (
                                    <span className="block text-xs text-gray-500">
                                      {p.part_description}
                                    </span>
                                  )}
                                </div>
                              </div>
                              <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-bold text-blue-700">
                                {p.quantity} adet
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Confidence progress bar */}
                    {detailParsed.confidence != null && (
                      <div>
                        <div className="mb-1.5 flex items-center justify-between">
                          <span className="text-xs font-semibold text-blue-700">Guven Skoru</span>
                          <span className="text-xs font-bold text-blue-800">
                            %{Math.round(detailParsed.confidence * 100)}
                          </span>
                        </div>
                        <div className="h-2 w-full overflow-hidden rounded-full bg-blue-200">
                          <div
                            className={`h-full rounded-full transition-all ${
                              detailParsed.confidence >= 0.8
                                ? 'bg-emerald-500'
                                : detailParsed.confidence >= 0.5
                                  ? 'bg-amber-500'
                                  : 'bg-rose-500'
                            }`}
                            style={{ width: `${Math.round(detailParsed.confidence * 100)}%` }}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Action buttons */}
            <div className="space-y-3 border-t border-gray-100 pt-5">
              {/* Primary actions row */}
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={reparseMutation.isPending}
                    onClick={() => reparseMutation.mutate(activeEmail!.id)}
                  >
                    Yeniden Ayrıştır
                  </Button>
                  {activeEmail.review_status === 'pending_review' && (
                    <>
                      <Button
                        size="sm"
                        loading={reviewMutation.isPending}
                        onClick={() =>
                          reviewMutation.mutate({ id: activeEmail!.id, action: 'approve' })
                        }
                        className="rounded-lg! bg-emerald-600! px-5! text-white! shadow-sm! hover:bg-emerald-700!"
                      >
                        Onayla
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={reviewMutation.isPending}
                        onClick={() =>
                          reviewMutation.mutate({ id: activeEmail!.id, action: 'reject' })
                        }
                        className="rounded-lg! border-rose-200! bg-rose-50! text-rose-600! hover:bg-rose-100!"
                      >
                        Reddet
                      </Button>
                    </>
                  )}
                </div>
                <Button variant="secondary" size="sm" onClick={() => setDetailEmail(null)}>
                  Kapat
                </Button>
              </div>

              {/* Approved actions row */}
              {activeEmail.review_status === 'approved' && (
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={createCustomerMutation.isPending}
                    onClick={() => handleCreateCustomer(activeEmail!)}
                    disabled={!detailParsed}
                  >
                    Müşteri Oluştur
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    loading={createQuoteMutation.isPending}
                    onClick={() => createQuoteMutation.mutate(activeEmail!.id)}
                    disabled={!detailParsed?.parts?.length}
                  >
                    Teklif Oluştur
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
