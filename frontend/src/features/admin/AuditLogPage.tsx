import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, RotateCcw, FileSearch } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { DataTable } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
import { Select } from '../../components/ui/Select';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
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

/**
 * Pretty-print a `changes` JSON blob for the detail modal. Falls
 * back to the raw string if the payload doesn't parse — better to
 * show *something* than to drop the field on a malformed entry.
 */
function formatChanges(raw: string | null | undefined): string {
  if (!raw) return '';
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw;
  }
}

export default function AuditLogPage() {
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<FilterState>(initialFilters);
  const [exporting, setExporting] = useState(false);
  // Selected row for the "Detay" modal that surfaces the raw
  // ``changes`` JSON. We keep this local rather than routing because
  // the data is purely advisory and shouldn't pollute browser
  // history with audit-id deep links.
  const [detailRow, setDetailRow] = useState<AuditLog | null>(null);

  const queryParams = buildQueryParams(filters, page);

  const { data, isLoading, isError, refetch } = useQuery<PaginatedAuditLogs>({
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

  // Map common audit action prefixes → Badge variants. Login/auth events
  // get `info`, KVKK gets `warning` (sensitive), exports get `default`.
  const actionTone = (action: string): 'default' | 'info' | 'warning' | 'success' | 'danger' => {
    if (action.startsWith('kvkk_')) return 'warning';
    if (action.startsWith('login') || action.startsWith('logout')) return 'info';
    if (action.includes('delete') || action.includes('reject')) return 'danger';
    if (action.includes('approve') || action.includes('create')) return 'success';
    return 'default';
  };

  const columns = [
    {
      key: 'created_at',
      header: 'Tarih',
      sortable: true,
      render: (row: AuditLog) => (
        <span className="whitespace-nowrap text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
          {formatDateTime(row.created_at)}
        </span>
      ),
    },
    {
      key: 'user',
      header: 'Kullanıcı',
      sortable: true,
      render: (row: AuditLog) => (
        <span className="text-[13px] font-medium text-slate-900 dark:text-white">
          {row.user_email ?? (row.user_id !== null ? `#${row.user_id}` : 'Sistem')}
        </span>
      ),
    },
    {
      key: 'action',
      header: 'İşlem',
      sortable: true,
      render: (row: AuditLog) => (
        <Badge variant={actionTone(row.action)} size="sm" dot>
          <span className="font-mono text-[11px]">{row.action}</span>
        </Badge>
      ),
    },
    {
      key: 'entity_type',
      header: 'Varlık',
      render: (row: AuditLog) => (
        <span className="text-[13px] text-slate-600 dark:text-slate-300">
          {row.entity_type}
          {row.entity_id != null && (
            <span className="ml-1 tabular-nums text-slate-400 dark:text-slate-500">
              #{row.entity_id}
            </span>
          )}
        </span>
      ),
    },
    {
      key: 'ip_address',
      header: 'IP',
      render: (row: AuditLog) => (
        <span className="font-mono text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
          {row.ip_address || '—'}
        </span>
      ),
    },
    {
      key: 'changes',
      header: 'Detay',
      // The ``changes`` column carries a JSON diff (before/after).
      // We surface it as an icon button so the table stays compact
      // — clicking opens a modal with the formatted payload.
      render: (row: AuditLog) =>
        row.changes ? (
          <button
            type="button"
            onClick={() => setDetailRow(row)}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[12px] text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
            aria-label="Değişiklik detayını görüntüle"
          >
            <FileSearch size={12} />
            Görüntüle
          </button>
        ) : (
          <span className="text-[12px] text-slate-400 dark:text-slate-500">—</span>
        ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Denetim Kayıtları"
        description={`Sistem işlem geçmişi · ${totalCount.toLocaleString('tr-TR')} kayıt`}
      >
        <Button
          variant="secondary"
          size="sm"
          onClick={handleCsvExport}
          loading={exporting}
          disabled={totalCount === 0}
        >
          <Download size={14} />
          CSV İndir
        </Button>
      </PageHeader>

      {/* Filter card — keeps all 6 filter inputs visually grouped on a
          slate-tinted surface. Reset button anchors to the bottom-right. */}
      <div className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
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
        <div className="mt-4 flex justify-end">
          <Button variant="tertiary" size="sm" onClick={resetFilters}>
            <RotateCcw size={13} />
            Filtreleri temizle
          </Button>
        </div>
      </div>

      {isError ? (
        <QueryErrorBanner variant="block" onRetry={() => refetch()} />
      ) : (
        <DataTable
          columns={columns}
          data={logs}
          loading={isLoading}
          emptyMessage="Denetim kaydı bulunamadı"
          page={page}
          totalPages={totalPages}
          onPageChange={setPage}
        />
      )}

      <Modal
        isOpen={detailRow !== null}
        onClose={() => setDetailRow(null)}
        title={detailRow ? `Denetim #${detailRow.id} — ${detailRow.action}` : 'Denetim Detayı'}
        size="lg"
      >
        {detailRow && (
          <div className="space-y-3">
            <dl className="grid grid-cols-2 gap-3 text-[13px]">
              <div>
                <dt className="text-overline text-slate-400">Tarih</dt>
                <dd className="text-slate-700 dark:text-slate-200">
                  {formatDateTime(detailRow.created_at)}
                </dd>
              </div>
              <div>
                <dt className="text-overline text-slate-400">Kullanıcı</dt>
                <dd className="text-slate-700 dark:text-slate-200">
                  {detailRow.user_email ?? `#${detailRow.user_id ?? '—'}`}
                </dd>
              </div>
              <div>
                <dt className="text-overline text-slate-400">Varlık</dt>
                <dd className="text-slate-700 dark:text-slate-200">
                  {detailRow.entity_type}
                  {detailRow.entity_id != null && ` #${detailRow.entity_id}`}
                </dd>
              </div>
              <div>
                <dt className="text-overline text-slate-400">IP</dt>
                <dd className="font-mono text-slate-700 dark:text-slate-200">
                  {detailRow.ip_address || '—'}
                </dd>
              </div>
            </dl>
            <div>
              <dt className="text-overline mb-1 text-slate-400">Değişiklikler (JSON)</dt>
              <pre className="max-h-96 overflow-auto rounded-lg border border-slate-200 bg-slate-50 p-3 font-mono text-[12px] text-slate-800 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-200">
                {formatChanges(detailRow.changes) || '— (değişiklik kaydı yok)'}
              </pre>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
