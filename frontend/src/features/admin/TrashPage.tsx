import { useState, useMemo, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { RotateCcw, Trash2, AlertCircle } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Select } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { BulkActionBar } from '../../components/ui/BulkActionBar';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { trashApi, type TrashedRow } from '../../lib/api';
import { formatDate } from '../../lib/formatters';

/**
 * D-030 — Trash / soft-delete restore console.
 *
 * Frontend for the F-007 backend (`/trash/{entity}` + restore). Operations
 * and sales managers can browse soft-deleted rows per entity and un-tombstone
 * them individually or in bulk. Tenant-scoped server-side; a foreign-tenant
 * row simply never appears in the list.
 *
 * Selection is page-managed (the DataTable primitive has no built-in
 * selection): a checkbox render-column tracks ids, a toolbar select-all
 * toggles the visible page, and the BulkActionBar drives bulk restore.
 */

const ENTITIES: { value: string; label: string }[] = [
  { value: 'customers', label: 'Müşteriler' },
  { value: 'leads', label: 'Leadler' },
  { value: 'opportunities', label: 'Fırsatlar' },
  { value: 'quotes', label: 'Teklifler' },
  { value: 'contracts', label: 'Sözleşmeler' },
  { value: 'invoices', label: 'Faturalar' },
  { value: 'email_requests', label: 'E-postalar' },
];

export default function TrashPage() {
  const queryClient = useQueryClient();
  const [entity, setEntity] = useState<string>('customers');
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [confirmBulk, setConfirmBulk] = useState(false);

  const queryKey = useMemo(() => ['trash', entity] as const, [entity]);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey,
    queryFn: () => trashApi.list(entity, 200),
  });

  const rows: TrashedRow[] = data?.items ?? [];

  const clearSelection = useCallback(() => setSelectedIds(new Set()), []);

  const switchEntity = useCallback((next: string) => {
    setEntity(next);
    setSelectedIds(new Set());
  }, []);

  const restoreMutation = useMutation({
    mutationFn: (id: number) => trashApi.restore(entity, id),
  });

  const restoreOne = useCallback(
    async (id: number) => {
      try {
        await restoreMutation.mutateAsync(id);
        toast.success(`Kayıt #${id} geri yüklendi`);
        await queryClient.invalidateQueries({ queryKey });
      } catch {
        toast.error(`#${id} geri yüklenemedi`);
      }
    },
    [restoreMutation, queryClient, queryKey],
  );

  const runBulkRestore = useCallback(async () => {
    setConfirmBulk(false);
    const ids = Array.from(selectedIds);
    // Restore sequentially so one failure doesn't abandon the rest, and
    // each success/failure is reported individually (matches the backend's
    // per-row 404-vs-200 contract — a row another admin already restored
    // surfaces as a single skip, not a batch abort).
    let ok = 0;
    let failed = 0;
    for (const id of ids) {
      try {
        await trashApi.restore(entity, id);
        ok += 1;
      } catch {
        failed += 1;
      }
    }
    if (ok > 0) toast.success(`${ok} kayıt geri yüklendi`);
    if (failed > 0) toast.error(`${failed} kayıt geri yüklenemedi`);
    clearSelection();
    await queryClient.invalidateQueries({ queryKey });
  }, [selectedIds, entity, clearSelection, queryClient, queryKey]);

  const toggleRow = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const allVisibleSelected = rows.length > 0 && rows.every((r) => selectedIds.has(r.id));
  const toggleAll = useCallback(() => {
    setSelectedIds((prev) => {
      if (rows.length > 0 && rows.every((r) => prev.has(r.id))) {
        return new Set();
      }
      return new Set(rows.map((r) => r.id));
    });
  }, [rows]);

  const columns = useMemo(
    () => [
      {
        key: 'select',
        header: '',
        width: '44px',
        render: (row: TrashedRow) => (
          <input
            type="checkbox"
            aria-label={`Satır ${row.id} seç`}
            checked={selectedIds.has(row.id)}
            onChange={(e) => {
              e.stopPropagation();
              toggleRow(row.id);
            }}
            onClick={(e) => e.stopPropagation()}
            className="h-4 w-4 cursor-pointer rounded border-slate-300 text-honeywell-red focus:ring-(--focus-ring) dark:border-slate-600"
          />
        ),
      },
      { key: 'id', header: 'ID', numeric: true, width: '80px' },
      {
        key: 'deleted_at',
        header: 'Silinme Tarihi',
        render: (row: TrashedRow) =>
          row.deleted_at ? formatDate(row.deleted_at) : '—',
      },
      {
        key: 'deleted_by',
        header: 'Silen',
        hideOn: 'sm' as const,
        render: (row: TrashedRow) => (row.deleted_by ? `#${row.deleted_by}` : '—'),
      },
      {
        key: 'delete_reason',
        header: 'Sebep',
        hideOn: 'md' as const,
        render: (row: TrashedRow) => row.delete_reason || '—',
      },
      {
        key: 'actions',
        header: '',
        align: 'right' as const,
        width: '120px',
        render: (row: TrashedRow) => (
          <Button
            variant="secondary"
            size="sm"
            onClick={(e) => {
              e.stopPropagation();
              void restoreOne(row.id);
            }}
          >
            <RotateCcw size={13} />
            Geri Yükle
          </Button>
        ),
      },
    ],
    [selectedIds, toggleRow, restoreOne],
  );

  const entityLabel = ENTITIES.find((e) => e.value === entity)?.label ?? entity;

  return (
    <div>
      <PageHeader
        title="Çöp Kutusu"
        description="Silinen kayıtları görüntüleyin ve geri yükleyin (soft-delete / F-007)"
      />

      {/* Info callout — restore is reversible, but hard-delete after the
          retention window is not. */}
      <div className="mb-6 flex items-start gap-3 rounded-2xl border border-sky-100 bg-sky-50/70 p-4 dark:border-sky-900/40 dark:bg-sky-950/20">
        <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-sky-100 text-sky-700 ring-1 ring-inset ring-sky-200 dark:bg-sky-900/40 dark:text-sky-300 dark:ring-sky-900/60">
          <Trash2 size={16} />
        </span>
        <div className="min-w-0 flex-1 text-[13px] leading-5 text-sky-900 dark:text-sky-200">
          <p className="font-semibold">Silinen kayıtlar burada saklanır.</p>
          <p className="mt-0.5 text-sky-800/90 dark:text-sky-300/80">
            Geri yükleme işlemi kaydı aktif duruma döndürür ve audit log'a yazılır. Saklama
            süresi dolduğunda kayıt kalıcı olarak silinir ve artık geri yüklenemez.
          </p>
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-full max-w-xs">
          <Select
            label="Varlık tipi"
            options={ENTITIES}
            value={entity}
            onChange={(e) => switchEntity(e.target.value)}
          />
        </div>
        {rows.length > 0 && (
          <Button variant="tertiary" size="sm" onClick={toggleAll}>
            {allVisibleSelected ? 'Seçimi temizle' : 'Tümünü seç'}
          </Button>
        )}
      </div>

      {isError && (
        <div className="mb-4 max-w-md">
          <QueryErrorBanner variant="inline" onRetry={() => refetch()} />
        </div>
      )}

      {!isError && !isLoading && rows.length === 0 && (
        <div className="flex items-center gap-2.5 rounded-2xl border border-slate-200 bg-white px-5 py-8 text-[13px] text-slate-500 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-400">
          <AlertCircle size={15} />
          {entityLabel} için çöp kutusunda kayıt yok.
        </div>
      )}

      {(isLoading || rows.length > 0) && (
        <DataTable
          columns={columns}
          data={rows}
          loading={isLoading}
          density="compact"
          emptyMessage={`${entityLabel} için silinmiş kayıt yok`}
        />
      )}

      <BulkActionBar
        selectedCount={selectedIds.size}
        actions={[{ key: 'restore', label: 'Seçilenleri Geri Yükle', variant: 'primary' }]}
        onAction={(key) => {
          if (key === 'restore') setConfirmBulk(true);
        }}
        onClearSelection={clearSelection}
      />

      <ConfirmDialog
        isOpen={confirmBulk}
        onClose={() => setConfirmBulk(false)}
        onConfirm={() => void runBulkRestore()}
        title="Seçili kayıtları geri yükle"
        message={`${selectedIds.size} adet ${entityLabel} kaydı aktif duruma döndürülecek. Devam edilsin mi?`}
        confirmLabel="Geri Yükle"
      />
    </div>
  );
}
