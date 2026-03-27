import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { quotesApi } from '../../lib/api';
import { formatCurrency, formatDate } from '../../lib/formatters';
import { STATUS_LABELS, STATUS_COLORS } from '../../lib/constants';
import type { Quote, PaginatedResponse } from '../../lib/types';

const STATUS_TABS = [
  { value: '', label: 'Tumu' },
  { value: 'draft', label: 'Taslak' },
  { value: 'pending_approval', label: 'Onay Bekliyor' },
  { value: 'approved', label: 'Onaylandi' },
  { value: 'sent', label: 'Gonderildi' },
];

export default function QuoteListPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [page, setPage] = useState(1);
  const [statusTab, setStatusTab] = useState(
    searchParams.get('status') || '',
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

  const columns = [
    {
      key: 'quote_number',
      header: 'Teklif No',
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
      header: 'Musteri',
      render: (row: Quote) => (
        <span className="text-sm">
          {row.customer?.company || row.customer?.name || '-'}
        </span>
      ),
    },
    {
      key: 'status',
      header: 'Durum',
      render: (row: Quote) => (
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
      key: 'grand_total',
      header: 'Toplam',
      sortable: true,
      render: (row: Quote) => (
        <span className="font-medium text-sm">
          {formatCurrency(row.grand_total, row.currency)}
        </span>
      ),
    },
    {
      key: 'currency',
      header: 'Para Birimi',
      render: (row: Quote) => (
        <span className="text-sm">{row.currency}</span>
      ),
    },
    {
      key: 'created_at',
      header: 'Tarih',
      sortable: true,
      render: (row: Quote) => (
        <span className="text-sm whitespace-nowrap">
          {formatDate(row.created_at)}
        </span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Teklifler" description="Teklif yonetimi">
        <Button onClick={() => navigate('/quotes/new')}>Yeni Teklif</Button>
      </PageHeader>

      {/* Status Tabs */}
      <div className="mb-4 flex flex-wrap gap-1 rounded-lg bg-gray-100 p-1">
        {STATUS_TABS.map((tab) => (
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
        emptyMessage="Henuz teklif bulunamadi"
        page={data?.page || page}
        totalPages={data?.pages || 1}
        onPageChange={setPage}
      />
    </div>
  );
}
