import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { PageHeader } from '../../components/ui/PageHeader';
import { DataTable } from '../../components/ui/DataTable';
import { Select } from '../../components/ui/Select';
import { auditApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';

interface AuditLog {
  id: number;
  created_at: string;
  user_email: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  ip_address: string;
}

interface PaginatedAuditLogs {
  items: AuditLog[];
  total: number;
  page: number;
  pages: number;
}

const ENTITY_TYPE_OPTIONS = [
  { value: '', label: 'Tumu' },
  { value: 'user', label: 'Kullanici' },
  { value: 'email', label: 'Email' },
  { value: 'quote', label: 'Teklif' },
  { value: 'customer', label: 'Musteri' },
  { value: 'part', label: 'Parca' },
  { value: 'price', label: 'Fiyat' },
  { value: 'settings', label: 'Ayarlar' },
];

const PAGE_SIZE = 25;

export default function AuditLogPage() {
  const [page, setPage] = useState(1);
  const [entityType, setEntityType] = useState('');

  const { data, isLoading } = useQuery<PaginatedAuditLogs>({
    queryKey: ['audit-logs', { page, entityType }],
    queryFn: () =>
      auditApi.getLogs({
        page,
        page_size: PAGE_SIZE,
        ...(entityType && { entity_type: entityType }),
      }),
  });

  const logs = data?.items ?? [];
  const totalPages = data?.pages ?? 1;

  const columns = [
    {
      key: 'created_at',
      header: 'Tarih',
      sortable: true,
      render: (row: AuditLog) => (
        <span className="text-sm text-gray-700">{formatDateTime(row.created_at)}</span>
      ),
    },
    {
      key: 'user_email',
      header: 'Kullanici',
      sortable: true,
      render: (row: AuditLog) => (
        <span className="text-sm font-medium text-gray-900">{row.user_email}</span>
      ),
    },
    {
      key: 'action',
      header: 'Islem',
      sortable: true,
      render: (row: AuditLog) => (
        <span className="inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">
          {row.action}
        </span>
      ),
    },
    {
      key: 'entity_type',
      header: 'Varlik',
      render: (row: AuditLog) => (
        <span className="text-sm text-gray-600">
          {row.entity_type}
          {row.entity_id != null && (
            <span className="ml-1 text-gray-400">#{row.entity_id}</span>
          )}
        </span>
      ),
    },
    {
      key: 'ip_address',
      header: 'IP',
      render: (row: AuditLog) => (
        <span className="font-mono text-xs text-gray-500">{row.ip_address || '-'}</span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Denetim Kayitlari"
        description="Sistem islem gecmisi"
      />

      <div className="mb-6 max-w-xs">
        <Select
          label="Varlik Tipi"
          options={ENTITY_TYPE_OPTIONS}
          value={entityType}
          onChange={(e) => {
            setEntityType(e.target.value);
            setPage(1);
          }}
        />
      </div>

      <DataTable
        columns={columns}
        data={logs}
        loading={isLoading}
        emptyMessage="Denetim kaydi bulunamadi"
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
      />
    </div>
  );
}
