import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { DataTable } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
import { emailsApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import {
  CATEGORY_LABELS,
  REVIEW_STATUS_LABELS,
  REVIEW_STATUS_COLORS,
  STATUS_LABELS,
  STATUS_COLORS,
} from '../../lib/constants';
import type { EmailRequest, PaginatedResponse } from '../../lib/types';

const REVIEW_TABS = [
  { value: '', label: 'Tumu' },
  { value: 'pending', label: 'Inceleme Bekleyen' },
  { value: 'approved', label: 'Onaylanan' },
  { value: 'rejected', label: 'Reddedilen' },
];

const CATEGORY_OPTIONS = [
  { value: '', label: 'Tum Kategoriler' },
  ...Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ value, label })),
];

export default function EmailListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [reviewTab, setReviewTab] = useState(searchParams.get('review_status') || '');
  const [category, setCategory] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [manualForm, setManualForm] = useState({
    from_address: '',
    subject: '',
    body_text: '',
  });

  const { data, isLoading } = useQuery<PaginatedResponse<EmailRequest>>({
    queryKey: ['emails', { page, search, review_status: reviewTab, category }],
    queryFn: () =>
      emailsApi.getEmails({
        page,
        page_size: 20,
        ...(search && { search }),
        ...(reviewTab && { review_status: reviewTab }),
        ...(category && { category }),
      }),
  });

  const pollMutation = useMutation({
    mutationFn: emailsApi.pollEmails,
    onSuccess: (res) => {
      toast.success(res.message || 'Email kontrolu tamamlandi');
      queryClient.invalidateQueries({ queryKey: ['emails'] });
    },
    onError: () => toast.error('Email kontrolu basarisiz'),
  });

  const createMutation = useMutation({
    mutationFn: (payload: typeof manualForm) => emailsApi.createManualEmail(payload),
    onSuccess: () => {
      toast.success('Email basariyla eklendi');
      setModalOpen(false);
      setManualForm({ from_address: '', subject: '', body_text: '' });
      queryClient.invalidateQueries({ queryKey: ['emails'] });
    },
    onError: () => toast.error('Email eklenemedi'),
  });

  const handleTabChange = useCallback(
    (tab: string) => {
      setReviewTab(tab);
      setPage(1);
      if (tab) {
        setSearchParams({ review_status: tab });
      } else {
        setSearchParams({});
      }
    },
    [setSearchParams],
  );

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
        <span className="max-w-[200px] truncate block">{row.from_address}</span>
      ),
    },
    {
      key: 'subject',
      header: 'Konu',
      render: (row: EmailRequest) => (
        <button
          type="button"
          onClick={() => navigate(`/emails/${row.id}`)}
          className="max-w-[260px] truncate block text-left font-medium text-honeywell-red hover:underline"
        >
          {row.subject || '(Konu yok)'}
        </button>
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

  return (
    <div>
      <PageHeader title="Emailler" description="Gelen email talepleri">
        <Button variant="secondary" onClick={() => setModalOpen(true)}>
          Manuel Email Ekle
        </Button>
        <Button loading={pollMutation.isPending} onClick={() => pollMutation.mutate()}>
          Email Kontrol
        </Button>
      </PageHeader>

      {/* Tabs */}
      <div className="mb-4 flex flex-wrap gap-1 rounded-lg bg-gray-100 p-1">
        {REVIEW_TABS.map((tab) => (
          <button
            key={tab.value}
            type="button"
            onClick={() => handleTabChange(tab.value)}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              reviewTab === tab.value
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

      {/* Table */}
      <DataTable
        columns={columns}
        data={data?.items || []}
        loading={isLoading}
        emptyMessage="Henuz email bulunamadi"
        page={data?.page || page}
        totalPages={data?.pages || 1}
        onPageChange={setPage}
      />

      {/* Manual Email Modal */}
      <Modal
        isOpen={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Manuel Email Ekle"
        size="lg"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate(manualForm);
          }}
          className="space-y-4"
        >
          <Input
            label="Gonderen"
            placeholder="ornek@sirket.com"
            value={manualForm.from_address}
            onChange={(e) =>
              setManualForm((p) => ({ ...p, from_address: e.target.value }))
            }
            required
          />
          <Input
            label="Konu"
            placeholder="Email konusu"
            value={manualForm.subject}
            onChange={(e) =>
              setManualForm((p) => ({ ...p, subject: e.target.value }))
            }
            required
          />
          <div className="w-full">
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Icerik
            </label>
            <textarea
              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm
                placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-honeywell-light
                focus:border-honeywell-red"
              rows={6}
              placeholder="Email icerigi..."
              value={manualForm.body_text}
              onChange={(e) =>
                setManualForm((p) => ({ ...p, body_text: e.target.value }))
              }
              required
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="secondary" onClick={() => setModalOpen(false)}>
              Iptal
            </Button>
            <Button type="submit" loading={createMutation.isPending}>
              Kaydet
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
