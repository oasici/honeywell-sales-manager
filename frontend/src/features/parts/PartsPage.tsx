import { useState, useRef, useCallback, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Upload, Info } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { DataTable } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import { partsApi } from '../../lib/api';
import { useT } from '../../hooks/useT';
import type { SparePart, PaginatedResponse } from '../../lib/types';

const CURRENCY_FORMATTER = new Intl.NumberFormat('tr-TR', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
});

function formatPrice(value: number | null | undefined): string {
  if (value == null) return '-';
  return CURRENCY_FORMATTER.format(value);
}

interface PartsImportResponse {
  imported: number;
  parts_created?: number;
  parts_updated?: number;
  prices_created?: number;
  skipped?: number;
}

function PartDetailModal({ part, onClose }: { part: SparePart | null; onClose: () => void }) {
  const t = useT();
  if (!part) return null;

  const hasPriceInfo = part.transfer_price != null || part.supplier_price != null;
  const descriptionTr = part.description_tr || part.name_tr;
  const descriptionEn = part.description_en || part.name_en;
  const createdDate = part.created_at?.split('T')[0];

  return (
    <Modal isOpen={!!part} onClose={onClose} title={part.honeywell_code} description={part.model_number || undefined} size="lg">
      <div className="space-y-5">
        {/* Info highlight (only when present). Amber tint signals "advisory"
            content that's still useful but not destructive. */}
        {part.info && (
          <div className="flex items-start gap-3 rounded-2xl border border-amber-100 bg-amber-50/70 px-4 py-3 dark:border-amber-900/40 dark:bg-amber-950/20">
            <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[10px] bg-amber-100 text-amber-700 ring-1 ring-inset ring-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-900/60">
              <Info size={14} />
            </span>
            <div className="min-w-0 flex-1 text-[13px] text-amber-900 dark:text-amber-200">
              <span className="font-semibold">{t('parts.modal_info')} </span>
              {part.info}
            </div>
          </div>
        )}

        {/* Price section — slate-tinted well, big tabular-nums values so the
            two prices align even with different magnitudes. Currency reads
            as a label badge, not a competing data point. */}
        <div className="rounded-2xl border border-slate-200 bg-slate-50/70 p-5 dark:border-slate-800 dark:bg-slate-900/40">
          {hasPriceInfo ? (
            <div className="flex flex-wrap items-end gap-8">
              {part.transfer_price != null && (
                <div>
                  <span className="text-overline text-slate-500 dark:text-slate-400">
                    {t('parts.tp_label')}
                  </span>
                  <p className="mt-1.5 text-[28px] font-bold leading-none tracking-tight tabular-nums text-slate-900 dark:text-white">
                    {formatPrice(part.transfer_price)}
                  </p>
                </div>
              )}
              {part.supplier_price != null && (
                <div>
                  <span className="text-overline text-slate-500 dark:text-slate-400">
                    {t('parts.lp_label')}
                  </span>
                  <p className="mt-1.5 text-[28px] font-bold leading-none tracking-tight tabular-nums text-slate-900 dark:text-white">
                    {formatPrice(part.supplier_price)}
                  </p>
                </div>
              )}
              {part.price_currency && (
                <span className="mb-1.5">
                  <Badge variant="default" size="md">
                    {part.price_currency}
                  </Badge>
                </span>
              )}
            </div>
          ) : (
            <p className="text-[13px] italic text-slate-400">{t('parts.no_price')}</p>
          )}
        </div>

        {/* Description card — language-tagged so TR/EN coexistence stays
            scannable. The chips use Badge primitives for visual consistency
            with the rest of the system. */}
        {(descriptionTr || descriptionEn) && (
          <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
            <h4 className="text-overline text-slate-500 dark:text-slate-400">
              {t('parts.description_heading')}
            </h4>
            <div className="mt-3 space-y-2.5 text-[13px] leading-6 text-slate-700 dark:text-slate-300">
              {descriptionTr && (
                <div className="flex items-start gap-2">
                  <Badge variant="info" size="sm">TR</Badge>
                  <span>{descriptionTr}</span>
                </div>
              )}
              {descriptionEn && (
                <div className="flex items-start gap-2">
                  <Badge variant="success" size="sm">EN</Badge>
                  <span>{descriptionEn}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Category + subcategory chips */}
        {(part.category || part.subcategory) && (
          <div className="flex flex-wrap gap-2">
            {part.category && (
              <Badge variant="default" size="md">{part.category}</Badge>
            )}
            {part.subcategory && (
              <Badge variant="default" size="md">{part.subcategory}</Badge>
            )}
          </div>
        )}

        {/* Created date — quietly anchored at the bottom */}
        {createdDate && (
          <p className="text-[12px] tabular-nums text-slate-400 dark:text-slate-500">
            {t('parts.created_label')} {createdDate}
          </p>
        )}
      </div>
    </Modal>
  );
}

export default function PartsPage() {
  const t = useT();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [selectedPart, setSelectedPart] = useState<SparePart | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const { data, isLoading } = useQuery<PaginatedResponse<SparePart>>({
    queryKey: ['parts', { page, search, category }],
    queryFn: () =>
      partsApi.getParts({
        page,
        page_size: 20,
        ...(search && { search }),
        ...(category && { category }),
      }),
  });

  const { data: categories } = useQuery<string[]>({
    queryKey: ['parts-categories'],
    queryFn: partsApi.getCategories,
  });

  const importMutation = useMutation<PartsImportResponse, Error, File>({
    mutationFn: (file: File) => partsApi.importParts(file) as Promise<PartsImportResponse>,
    onSuccess: (res) => {
      const parts = (res.parts_created || 0) + (res.parts_updated || 0);
      const skipped = res.skipped
        ? t('parts.import_skipped').replace('{n}', String(res.skipped))
        : '';
      toast.success(
        t('parts.import_success')
          .replace('{total}', String(parts))
          .replace('{created}', String(res.parts_created || 0))
          .replace('{updated}', String(res.parts_updated || 0))
          .replace('{skipped}', skipped),
      );
      queryClient.invalidateQueries({ queryKey: ['parts'] });
      queryClient.invalidateQueries({ queryKey: ['parts-categories'] });
    },
    onError: () => toast.error(t('parts.import_failed')),
  });

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) importMutation.mutate(file);
    e.target.value = '';
  };

  const handleRowClick = useCallback((part: SparePart) => {
    setSelectedPart(part);
  }, []);

  const categoryOptions = useMemo(
    () => [
      { value: '', label: t('parts.all_categories') },
      ...(categories || []).map((c) => ({ value: c, label: c })),
    ],
    [categories, t],
  );

  const columns = useMemo(
    () => [
      {
        key: 'model_number',
        header: t('parts.col_model'),
        sortable: true,
        render: (row: SparePart) => (
          <span className="font-mono text-[13px] font-semibold text-slate-900 dark:text-white">
            {row.model_number || row.honeywell_code}
          </span>
        ),
      },
      {
        key: 'honeywell_code',
        header: t('parts.col_hw_code'),
        sortable: true,
        render: (row: SparePart) => (
          <span className="font-mono text-[12px] text-slate-500 dark:text-slate-400">
            {row.honeywell_code}
          </span>
        ),
      },
      {
        key: 'name_tr',
        header: t('parts.col_name'),
        render: (row: SparePart) => (
          <span
            className="text-[13px] text-slate-700 dark:text-slate-200"
            title={row.description_tr || row.name_tr || ''}
          >
            {row.name_tr || row.name_en || '—'}
          </span>
        ),
      },
      {
        key: 'category',
        header: t('parts.col_category'),
        render: (row: SparePart) =>
          row.category ? (
            <Badge variant="default" size="sm">{row.category}</Badge>
          ) : (
            <span className="text-[12px] text-slate-400">—</span>
          ),
      },
      {
        key: 'transfer_price',
        header: t('parts.col_tp'),
        align: 'right' as const,
        numeric: true,
        render: (row: SparePart) => (
          <span className="text-[13px] font-semibold tabular-nums text-slate-900 dark:text-white">
            {row.transfer_price != null
              ? `${formatPrice(row.transfer_price)}${row.price_currency ? ` ${row.price_currency}` : ''}`
              : '—'}
          </span>
        ),
      },
      {
        key: 'supplier_price',
        header: t('parts.col_lp'),
        align: 'right' as const,
        numeric: true,
        render: (row: SparePart) => (
          <span className="text-[13px] tabular-nums text-slate-600 dark:text-slate-300">
            {row.supplier_price != null
              ? `${formatPrice(row.supplier_price)}${row.price_currency ? ` ${row.price_currency}` : ''}`
              : '—'}
          </span>
        ),
      },
    ],
    [t],
  );

  return (
    <div>
      <PageHeader title={t('parts.catalog_title')} description={t('parts.catalog_subtitle')}>
        <input
          type="file"
          ref={fileRef}
          onChange={handleImport}
          accept=".xlsx,.xls,.csv,.json,.pdf"
          className="hidden"
        />
        <Button loading={importMutation.isPending} onClick={() => fileRef.current?.click()}>
          <Upload size={14} />
          {t('parts.import_btn')}
        </Button>
      </PageHeader>

      {/* Format hint banner — slate-tinted info row, calmer than the old
          blue alert. Icon medallion makes it clear this is advisory,
          not a CTA. */}
      <div className="mb-4 flex items-start gap-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-3.5 dark:border-slate-800 dark:bg-slate-900/40">
        <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-[10px] bg-white text-slate-500 ring-1 ring-inset ring-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700">
          <Info size={14} />
        </span>
        <p className="min-w-0 flex-1 text-[13px] leading-5 text-slate-600 dark:text-slate-300">
          {t('parts.excel_format_banner')}
        </p>
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="w-72">
          <Input
            placeholder={t('parts.search_ph')}
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

      {/* Table */}
      <DataTable
        columns={columns}
        data={data?.items || []}
        loading={isLoading}
        emptyMessage={t('parts.empty')}
        page={data?.page || page}
        totalPages={data?.pages || 1}
        onPageChange={setPage}
        onRowClick={handleRowClick}
      />

      {/* Product detail modal */}
      <PartDetailModal part={selectedPart} onClose={() => setSelectedPart(null)} />
    </div>
  );
}
