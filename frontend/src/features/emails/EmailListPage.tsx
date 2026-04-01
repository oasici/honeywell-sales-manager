import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Mail, User, Building2, Clock, Tag, FileText } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { DataTable } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import { emailsApi, customersApi, quotesApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import {
  CATEGORY_LABELS,
  REVIEW_STATUS_LABELS,
  REVIEW_STATUS_COLORS,
  STATUS_LABELS,
  STATUS_COLORS,
} from '../../lib/constants';
import type { EmailRequest, PaginatedResponse } from '../../lib/types';

const READ_TABS = [
  { value: '', label: 'Okunmamis' },
  { value: 'read', label: 'Okunmus' },
];

const CATEGORY_OPTIONS = [
  { value: '', label: 'Tum Kategoriler' },
  ...Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ value, label })),
];

export default function EmailListPage() {
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
      toast.success(res.message || 'Email kontrolu tamamlandi');
      queryClient.invalidateQueries({ queryKey: ['emails'] });
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.error?.message || 'Email kontrolu basarisiz';
      toast.error(msg);
    },
  });

  const createCustomerMutation = useMutation({
    mutationFn: (payload: { name: string; email: string; company?: string }) =>
      customersApi.createCustomer(payload),
    onSuccess: (customer) => {
      toast.success(`Musteri olusturuldu: ${customer.name}`);
      queryClient.invalidateQueries({ queryKey: ['customers'] });
    },
    onError: () => toast.error('Musteri olusturulamadi (zaten mevcut olabilir)'),
  });

  const createQuoteMutation = useMutation({
    mutationFn: (emailId: number) => quotesApi.createQuoteFromEmail(emailId),
    onSuccess: (quote) => {
      toast.success(`Taslak teklif olusturuldu: ${quote.quote_number}`);
      setDetailEmail(null);
      navigate(`/quotes/${quote.id}`);
    },
    onError: () => toast.error('Teklif olusturulamadi'),
  });

  const reparseMutation = useMutation({
    mutationFn: (emailId: number) => emailsApi.reparseEmail(emailId),
    onSuccess: (res) => {
      toast.success(res.message || 'Email yeniden ayristirildi');
      queryClient.invalidateQueries({ queryKey: ['emails'] });
      if (detailEmail) {
        queryClient.invalidateQueries({ queryKey: ['email-detail', detailEmail.id] });
      }
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.error?.message || 'Ayristirma basarisiz';
      toast.error(msg);
    },
  });

  const [editingParse, setEditingParse] = useState(false);
  const [editForm, setEditForm] = useState<Record<string, any>>({});

  const correctMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Record<string, unknown> }) =>
      emailsApi.correctParse(id, data),
    onSuccess: (res) => {
      toast.success(res.message);
      setEditingParse(false);
      queryClient.invalidateQueries({ queryKey: ['emails'] });
      if (detailEmail) {
        queryClient.invalidateQueries({ queryKey: ['email-detail', detailEmail.id] });
      }
    },
    onError: (err: any) => {
      toast.error(err?.response?.data?.error?.message || 'Duzeltme kaydedilemedi');
    },
  });

  const reviewMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: string }) => emailsApi.reviewEmail(id, action),
    onSuccess: () => {
      toast.success('Inceleme tamamlandi');
      queryClient.invalidateQueries({ queryKey: ['emails'] });
      setDetailEmail(null);
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.error?.message || 'Inceleme basarisiz';
      toast.error(msg);
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
      toast.error('Email henuz ayristirilmamis');
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

  const columns = [
    {
      key: 'received_at',
      header: 'Tarih',
      sortable: true,
      render: (row: EmailRequest) => (
        <span className="whitespace-nowrap text-sm">
          {formatDateTime(row.received_at || row.created_at)}
        </span>
      ),
    },
    {
      key: 'from_address',
      header: 'Gonderen',
      render: (row: EmailRequest) => (
        <span className="max-w-[200px] truncate block text-sm">{row.from_address}</span>
      ),
    },
    {
      key: 'subject',
      header: 'Konu',
      render: (row: EmailRequest) => (
        <span className="max-w-[260px] truncate block text-sm font-medium text-honeywell-red">
          {row.subject || '(Konu yok)'}
        </span>
      ),
    },
    {
      key: 'category',
      header: 'Kategori',
      render: (row: EmailRequest) => (
        <span className="text-sm">
          {row.category ? CATEGORY_LABELS[row.category] || row.category : '-'}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Durum',
      render: (row: EmailRequest) => (
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
            STATUS_COLORS[row.status] || 'bg-gray-100 text-gray-700'
          }`}
        >
          {STATUS_LABELS[row.status] || row.status}
        </span>
      ),
    },
    {
      key: 'review_status',
      header: 'Inceleme',
      render: (row: EmailRequest) => {
        const rs = row.review_status;
        if (!rs) return <span className="text-gray-400 text-sm">-</span>;
        return (
          <span
            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
              REVIEW_STATUS_COLORS[rs] || 'bg-gray-100 text-gray-700'
            }`}
          >
            {REVIEW_STATUS_LABELS[rs] || rs}
          </span>
        );
      },
    },
  ];

  const detailParsed = activeEmail ? getParsedData(activeEmail) : null;

  return (
    <div>
      <PageHeader title="Emailler" description="Gelen email talepleri">
        <Button loading={pollMutation.isPending} onClick={() => pollMutation.mutate()}>
          Email Kontrol
        </Button>
      </PageHeader>

      {/* Tabs */}
      <div className="mb-4 flex flex-wrap gap-1 rounded-lg bg-gray-100 p-1">
        {READ_TABS.map((tab) => (
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
            placeholder="Email veya konu ara..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <div className="w-48">
          <Select
            options={CATEGORY_OPTIONS}
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
        emptyMessage="Henuz email bulunamadi"
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
        title="Email Detayi"
        size="lg"
      >
        {activeEmail && (
          <div className="space-y-4">
            {/* Header info */}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div className="flex items-start gap-2">
                <Mail size={16} className="mt-0.5 shrink-0 text-gray-400" />
                <div>
                  <span className="text-xs text-gray-500">Gonderen</span>
                  <p className="text-sm font-medium text-gray-900">{activeEmail.from_address}</p>
                </div>
              </div>
              <div className="flex items-start gap-2">
                <Clock size={16} className="mt-0.5 shrink-0 text-gray-400" />
                <div>
                  <span className="text-xs text-gray-500">Tarih</span>
                  <p className="text-sm text-gray-900">
                    {formatDateTime(activeEmail.received_at || activeEmail.created_at)}
                  </p>
                </div>
              </div>
            </div>

            {/* Subject */}
            <div className="flex items-start gap-2">
              <FileText size={16} className="mt-0.5 shrink-0 text-gray-400" />
              <div>
                <span className="text-xs text-gray-500">Konu</span>
                <p className="text-sm font-semibold text-gray-900">
                  {activeEmail.subject || '(Konu yok)'}
                </p>
              </div>
            </div>

            {/* Body */}
            <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
              <span className="mb-2 block text-xs font-medium text-gray-500">Email Icerigi</span>
              <div
                className="max-h-64 overflow-y-auto text-sm text-gray-700 leading-relaxed"
              >
                <p className="whitespace-pre-wrap">
                  {activeEmail.body_text
                    ? activeEmail.body_text.includes('<')
                      ? activeEmail.body_text
                          .replace(/<(style|script)[^>]*>[\s\S]*?<\/\1>/gi, '')
                          .replace(/<br\s*\/?>/gi, '\n')
                          .replace(/<\/?(p|div|tr|li|h[1-6])[^>]*>/gi, '\n')
                          .replace(/<[^>]+>/g, '')
                          .replace(/&nbsp;/g, ' ')
                          .replace(/&amp;/g, '&')
                          .replace(/&lt;/g, '<')
                          .replace(/&gt;/g, '>')
                          .replace(/&quot;/g, '"')
                          .replace(/\n\s*\n+/g, '\n\n')
                          .trim()
                      : activeEmail.body_text
                    : '(Icerik yok)'}
                </p>
              </div>
            </div>

            {/* Status badges */}
            <div className="flex flex-wrap gap-2">
              {activeEmail.category && (
                <Badge variant="info">
                  <Tag size={12} className="mr-1" />
                  {CATEGORY_LABELS[activeEmail.category] || activeEmail.category}
                </Badge>
              )}
              {activeEmail.status && (
                <Badge variant={activeEmail.status === 'parsed' ? 'success' : 'default'}>
                  {STATUS_LABELS[activeEmail.status] || activeEmail.status}
                </Badge>
              )}
              {activeEmail.review_status && (
                <Badge
                  variant={
                    activeEmail.review_status === 'approved'
                      ? 'success'
                      : activeEmail.review_status === 'rejected'
                        ? 'danger'
                        : 'warning'
                  }
                >
                  {REVIEW_STATUS_LABELS[activeEmail.review_status] || activeEmail.review_status}
                </Badge>
              )}
            </div>

            {/* Parsed data - editable */}
            {detailParsed && (
              <div className="space-y-3 rounded-lg border border-blue-200 bg-blue-50 p-4">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-blue-700">
                    AI Ayristirma Sonucu
                  </h4>
                  <button
                    type="button"
                    onClick={() => {
                      if (!editingParse) {
                        setEditForm({ ...detailParsed });
                      }
                      setEditingParse(!editingParse);
                    }}
                    className="text-xs text-blue-600 hover:text-blue-800 transition-colors"
                  >
                    {editingParse ? 'Iptal' : 'Duzenle'}
                  </button>
                </div>

                {editingParse ? (
                  <div className="space-y-3">
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      <div>
                        <label className="text-xs text-blue-600">Musteri</label>
                        <input
                          className="mt-1 w-full rounded border border-blue-200 bg-white px-2 py-1 text-sm"
                          value={editForm.customer_name || ''}
                          onChange={(e) => setEditForm((f: Record<string, any>) => ({ ...f, customer_name: e.target.value }))}
                        />
                      </div>
                      <div>
                        <label className="text-xs text-blue-600">Sirket</label>
                        <input
                          className="mt-1 w-full rounded border border-blue-200 bg-white px-2 py-1 text-sm"
                          value={editForm.customer_company || ''}
                          onChange={(e) => setEditForm((f: Record<string, any>) => ({ ...f, customer_company: e.target.value }))}
                        />
                      </div>
                    </div>
                    <div>
                      <label className="text-xs text-blue-600">Kategori</label>
                      <input
                        className="mt-1 w-full rounded border border-blue-200 bg-white px-2 py-1 text-sm"
                        value={editForm.category || ''}
                        onChange={(e) => setEditForm((f: Record<string, any>) => ({ ...f, category: e.target.value }))}
                      />
                    </div>
                    <button
                      type="button"
                      onClick={() => correctMutation.mutate({ id: activeEmail!.id, data: editForm })}
                      disabled={correctMutation.isPending}
                      className="rounded bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700 disabled:opacity-50"
                    >
                      {correctMutation.isPending ? 'Kaydediliyor...' : 'Duzeltmeyi Kaydet'}
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                      {detailParsed.customer_name && (
                        <div className="flex items-center gap-2">
                          <User size={14} className="text-blue-500" />
                          <span className="text-sm"><strong>Musteri:</strong> {detailParsed.customer_name}</span>
                        </div>
                      )}
                      {detailParsed.customer_company && (
                        <div className="flex items-center gap-2">
                          <Building2 size={14} className="text-blue-500" />
                          <span className="text-sm"><strong>Sirket:</strong> {detailParsed.customer_company}</span>
                        </div>
                      )}
                    </div>
                    {detailParsed.parts && detailParsed.parts.length > 0 && (
                      <div>
                        <span className="text-xs font-medium text-blue-600">
                          Talep Edilen Parcalar ({detailParsed.parts.length})
                        </span>
                        <div className="mt-1 space-y-1">
                          {detailParsed.parts.map((p: any, i: number) => (
                            <div key={i} className="flex items-center justify-between rounded bg-white px-3 py-1.5 text-sm">
                              <span className="font-mono font-semibold text-gray-800">{p.part_code}</span>
                              <span className="text-gray-600">{p.part_description}</span>
                              <span className="font-medium">{p.quantity} adet</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    {detailParsed.confidence != null && (
                      <div className="text-xs text-blue-600">
                        Guven Skoru: %{Math.round(detailParsed.confidence * 100)}
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-col gap-3 border-t border-gray-200 pt-4">
              {/* Row 1: Parse & Review */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={reparseMutation.isPending}
                    onClick={() => reparseMutation.mutate(activeEmail!.id)}
                  >
                    Yeniden Ayristir
                  </Button>
                  {activeEmail.review_status === 'pending_review' && (
                    <>
                      <Button
                        size="sm"
                        loading={reviewMutation.isPending}
                        onClick={() => reviewMutation.mutate({ id: activeEmail!.id, action: 'approve' })}
                        className="!bg-green-600 !text-white hover:!bg-green-700"
                      >
                        Onayla
                      </Button>
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={reviewMutation.isPending}
                        onClick={() => reviewMutation.mutate({ id: activeEmail!.id, action: 'reject' })}
                        className="!bg-red-100 !text-red-700 hover:!bg-red-200"
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
              {/* Row 2: Customer & Quote (only for approved) */}
              {activeEmail.review_status === 'approved' && (
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    loading={createCustomerMutation.isPending}
                    onClick={() => handleCreateCustomer(activeEmail!)}
                    disabled={!detailParsed}
                  >
                    Musteri Olustur
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    loading={createQuoteMutation.isPending}
                    onClick={() => createQuoteMutation.mutate(activeEmail!.id)}
                    disabled={!detailParsed?.parts?.length}
                  >
                    Teklif Olustur
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
