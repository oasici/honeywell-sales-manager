import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { DataTable } from '../../components/ui/DataTable';
import { Select } from '../../components/ui/Select';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { auditApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';

interface AuditLog {
  id: number;
  created_at: string;
  user_id: number | null;
  user_email?: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  ip_address: string | null;
  changes?: string | null;
}

interface PaginatedAuditLogs {
  items: AuditLog[];
  total: number;
  page: number;
  pages: number;
}

interface FilterState {
  entityType: string;
  entityId: string;
  actionPrefix: string;
  userId: string;
  since: string;
  until: string;
}

const ENTITY_TYPE_OPTIONS = [
  { value: '', label: 'Tumu' },
  { value: 'user', label: 'Kullanıcı' },
  { value: 'email_request', label: 'Email' },
  { value: 'quote', label: 'Teklif' },
  { value: 'customer', label: 'Müşteri' },
  { value: 'opportunity', label: 'Fırsat' },
  { value: 'part', label: 'Parça' },
  { value: 'price', label: 'Fiyat' },
  { value: 'settings', label: 'Ayarlar' },
];

const ACTION_PREFIX_OPTIONS = [
  { value: '', label: 'Tum islemler' },
  { value: 'kvkk_', label: 'KVKK islemleri' },
  { value: 'login', label: 'Login olaylari' },
  { value: 'export', label: 'Disa aktarmalar' },
];

const PAGE_SIZE = 25;

const initialFilters: FilterState = {
  entityType: '',
  entityId: '',
  actionPrefix: '',
  userId: '',
  since: '',
  until: '',
};

function buildQueryParams(filters: FilterState, page: number): Record<string, unknown> {
  const params: Record<string, unknown> = {
    page,
    page_size: PAGE_SIZE,
  };
  if (filters.entityType) params.entity_type = filters.entityType;
  if (filters.entityId) params.entity_id = Number(filters.entityId);
  if (filters.actionPrefix) params.action_prefix = filters.actionPrefix;
  if (filters.userId) params.user_id = Number(filters.userId);
  if (filters.since) params.since = new Date(filters.since).toISOString();
  if (filters.until) params.until = new Date(filters.until).toISOString();
  return params;
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export default function AuditLogPage() {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<FilterState>(initialFilters);
  const [exporting, setExporting] = useState(false);

  const queryParams = buildQueryParams(filters, page);

  const { data, isLoading } = useQuery<PaginatedAuditLogs>({
    queryKey: ['audit-logs', queryParams],
    queryFn: () => auditApi.getLogs(queryParams),
  });

  const logs = data?.items ?? [];
  const totalPages = data?.pages ?? 1;
  const totalCount = data?.total ?? 0;

  const updateFilter = <K extends keyof FilterState>(key: K, value: FilterState[K]) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPage(1);
  };

  const resetFilters = () => {
    setFilters(initialFilters);
    setPage(1);
  };

  const handleCsvExport = async () => {
    setExporting(true);
    try {
      const params: Record<string, unknown> = {};
      if (filters.entityType) params.entity_type = filters.entityType;
      if (filters.entityId) params.entity_id = Number(filters.entityId);
      if (filters.actionPrefix) params.action_prefix = filters.actionPrefix;
      if (filters.userId) params.user_id = Number(filters.userId);
      if (filters.since) params.since = new Date(filters.since).toISOString();
      if (filters.until) params.until = new Date(filters.until).toISOString();

      const blob = await auditApi.exportCsv(params);
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
      downloadBlob(blob, `audit-logs-${stamp}.csv`);
    } finally {
      setExporting(false);
    }
  };

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
      key: 'user',
      header: 'Kullanıcı',
      sortable: true,
      render: (row: AuditLog) => (
        <span className="text-sm font-medium text-gray-900">
          {row.user_email ?? (row.user_id !== null ? `#${row.user_id}` : 'Sistem')}
        </span>
      ),
    },
    {
      key: 'action',
      header: 'İşlem',
      sortable: true,
      render: (row: AuditLog) => (
        <span className="inline-flex rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-700">
          {row.action}
        </span>
      ),
    },
    {
      key: 'entity_type',
      header: 'Varlık',
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
        title="Denetim Kayıtları"
        description={`Sistem işlem gecmisi (${totalCount} kayıt)`}
      >
        <Button
          variant="secondary"
          size="sm"
          onClick={handleCsvExport}
          disabled={exporting || totalCount === 0}
        >
          <Download size={16} className="mr-1.5" />
          {exporting ? 'Indiriliyor...' : 'CSV İndir'}
        </Button>
      </PageHeader>

      <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Select
          label="Varlık Tipi"
          options={ENTITY_TYPE_OPTIONS}
          value={filters.entityType}
          onChange={(e) => updateFilter('entityType', e.target.value)}
        />
        <Select
          label="İşlem Tipi"
          options={ACTION_PREFIX_OPTIONS}
          value={filters.actionPrefix}
          onChange={(e) => updateFilter('actionPrefix', e.target.value)}
        />
        <Input
          label="Varlık ID"
          type="number"
          inputMode="numeric"
          value={filters.entityId}
          onChange={(e) => updateFilter('entityId', e.target.value)}
          placeholder="örn. 42"
        />
        <Input
          label="Kullanıcı ID"
          type="number"
          inputMode="numeric"
          value={filters.userId}
          onChange={(e) => updateFilter('userId', e.target.value)}
          placeholder="örn. 7"
        />
        <Input
          label="Başlangıç"
          type="datetime-local"
          value={filters.since}
          onChange={(e) => updateFilter('since', e.target.value)}
        />
        <Input
          label="Bitiş"
          type="datetime-local"
          value={filters.until}
          onChange={(e) => updateFilter('until', e.target.value)}
        />
      </div>

      <div className="mb-4 flex justify-end">
        <Button variant="ghost" size="sm" onClick={resetFilters}>
          Filtreleri temizle
        </Button>
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
