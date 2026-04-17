import { useState, useRef, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { DataTable } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
import { partsApi } from '../../lib/api';
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

function PartDetailModal({
  part,
  onClose,
}: {
  part: SparePart | null;
  onClose: () => void;
}) {
  if (!part) return null;

  const hasPriceInfo = part.transfer_price != null || part.supplier_price != null;
  const descriptionTr = part.description_tr || part.name_tr;
  const descriptionEn = part.description_en || part.name_en;
  const createdDate = part.created_at?.split('T')[0];

  return (
    <Modal isOpen={!!part} onClose={onClose} title="" size="lg">
      <div className="space-y-5">
        {/* Gradient header banner */}
        <div className="-mx-6 -mt-6 rounded-t-2xl bg-gradient-to-r from-red-700 to-red-500 px-6 py-6">
          <h3 className="text-2xl font-bold tracking-tight text-white">
            {part.honeywell_code}
          </h3>
          {part.model_number && (
            <p className="mt-1 text-sm text-red-100">{part.model_number}</p>
          )}
        </div>

        {/* Info highlight box */}
        {part.info && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-700 dark:bg-amber-900/20 dark:text-amber-200">
            <span className="font-semibold">Bilgi: </span>
            {part.info}
          </div>
        )}

        {/* Price section */}
        <div className="rounded-2xl border border-gray-100 bg-gray-50 p-5 dark:border-gray-700 dark:bg-gray-800">
          {hasPriceInfo ? (
            <div className="flex flex-wrap items-end gap-8">
              {part.transfer_price != null && (
                <div>
                  <span className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    T.P. (Transfer Price)
                  </span>
                  <p className="mt-1 text-3xl font-bold text-gray-900 dark:text-white">
                    {formatPrice(part.transfer_price)}
                  </p>
                </div>
              )}
              {part.supplier_price != null && (
                <div>
                  <span className="text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                    L.P. (List Price)
                  </span>
                  <p className="mt-1 text-3xl font-bold text-gray-900 dark:text-white">
                    {formatPrice(part.supplier_price)}
                  </p>
                </div>
              )}
              {part.price_currency && (
                <span className="mb-1 inline-flex items-center rounded-full bg-gradient-to-r from-gray-200 to-gray-300 px-3 py-1 text-xs font-semibold text-gray-700 dark:from-gray-600 dark:to-gray-700 dark:text-gray-200">
                  {part.price_currency}
                </span>
              )}
            </div>
          ) : (
            <p className="text-sm text-gray-400 italic">Fiyat bilgisi yok</p>
          )}
        </div>

        {/* Gradient divider */}
        <div className="h-px bg-gradient-to-r from-transparent via-red-200 to-transparent dark:via-red-800" />

        {/* Description card */}
        {(descriptionTr || descriptionEn) && (
          <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm dark:border-gray-700 dark:bg-gray-800">
            <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-gray-400">
              Açıklama
            </h4>
            <div className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
              {descriptionTr && (
                <div className="flex gap-2">
                  <span className="inline-flex h-5 items-center rounded bg-blue-100 px-1.5 text-[10px] font-bold text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
                    TR
                  </span>
                  <span>{descriptionTr}</span>
                </div>
              )}
              {descriptionEn && (
                <div className="flex gap-2">
                  <span className="inline-flex h-5 items-center rounded bg-emerald-100 px-1.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                    EN
                  </span>
                  <span>{descriptionEn}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Metadata: Category & Subcategory pills */}
        <div className="flex flex-wrap gap-2">
          {part.category && (
            <span className="inline-flex items-center rounded-full bg-gradient-to-r from-indigo-50 to-indigo-100 px-3 py-1 text-xs font-medium text-indigo-700 ring-1 ring-inset ring-indigo-200 dark:from-indigo-900/30 dark:to-indigo-800/30 dark:text-indigo-300 dark:ring-indigo-700">
              {part.category}
            </span>
          )}
          {part.subcategory && (
            <span className="inline-flex items-center rounded-full bg-gradient-to-r from-violet-50 to-violet-100 px-3 py-1 text-xs font-medium text-violet-700 ring-1 ring-inset ring-violet-200 dark:from-violet-900/30 dark:to-violet-800/30 dark:text-violet-300 dark:ring-violet-700">
              {part.subcategory}
            </span>
          )}
        </div>

        {/* Created date footer */}
        {createdDate && (
          <p className="text-xs text-gray-400">
            Olusturma: {createdDate}
          </p>
        )}
      </div>
    </Modal>
  );
}

export default function PartsPage() {
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
      toast.success(
        `${parts} parça (${res.parts_created || 0} yeni, ${res.parts_updated || 0} guncellendi)` +
        (res.skipped ? `, ${res.skipped} atlandi` : '') +
        ' içe aktarıldı',
      );
      queryClient.invalidateQueries({ queryKey: ['parts'] });
      queryClient.invalidateQueries({ queryKey: ['parts-categories'] });
    },
    onError: () => toast.error('Katalog içe aktarimi başarısız'),
  });

  const handleImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) importMutation.mutate(file);
    e.target.value = '';
  };

  const handleRowClick = useCallback((part: SparePart) => {
    setSelectedPart(part);
  }, []);

  const categoryOptions = [
    { value: '', label: 'Tüm Kategoriler' },
    ...(categories || []).map((c) => ({ value: c, label: c })),
  ];

  const columns = [
    {
      key: 'model_number',
      header: 'Model No',
      sortable: true,
      render: (row: SparePart) => (
        <span className="font-mono text-sm font-semibold text-gray-900">
          {row.model_number || row.honeywell_code}
        </span>
      ),
    },
    {
      key: 'honeywell_code',
      header: 'Honeywell Kodu',
      sortable: true,
      render: (row: SparePart) => (
        <span className="font-mono text-xs text-gray-600">
          {row.honeywell_code}
        </span>
      ),
    },
    {
      key: 'name_tr',
      header: 'Tanim',
      render: (row: SparePart) => (
        <span className="text-sm" title={row.description_tr || row.name_tr || ''}>
          {row.name_tr || row.name_en || '-'}
        </span>
      ),
    },
    {
      key: 'category',
      header: 'Kategori',
      render: (row: SparePart) => (
        <span className="text-sm">{row.category || '-'}</span>
      ),
    },
    {
      key: 'transfer_price',
      header: 'T.P.',
      render: (row: SparePart) => (
        <span className="text-sm font-medium text-gray-900">
          {row.transfer_price != null
            ? `${formatPrice(row.transfer_price)} ${row.price_currency || ''}`
            : '-'}
        </span>
      ),
    },
    {
      key: 'supplier_price',
      header: 'L.P.',
      render: (row: SparePart) => (
        <span className="text-sm text-gray-700">
          {row.supplier_price != null
            ? `${formatPrice(row.supplier_price)} ${row.price_currency || ''}`
            : '-'}
        </span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Yedek Parçalar" description="Honeywell yedek parça katalogu">
        <input
          type="file"
          ref={fileRef}
          onChange={handleImport}
          accept=".xlsx,.xls,.csv,.json,.pdf"
          className="hidden"
        />
        <Button
          loading={importMutation.isPending}
          onClick={() => fileRef.current?.click()}
        >
          İçe Aktar (Excel/CSV/PDF)
        </Button>
      </PageHeader>

      {/* Info banner */}
      <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
        <strong>Excel Formati:</strong> Model No / Honeywell Code (zorunlu), açıklama, transfer price,
        supplier price sutunlarini iceren tek bir dosya yukleyin. Sutun eslestirme otomatik yapilir.
      </div>

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-4">
        <div className="w-72">
          <Input
            placeholder="Kod veya isim ile ara..."
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

      {/* Table */}
      <DataTable
        columns={columns}
        data={data?.items || []}
        loading={isLoading}
        emptyMessage="Henüz parça bulunamadi"
        page={data?.page || page}
        totalPages={data?.pages || 1}
        onPageChange={setPage}
        onRowClick={handleRowClick}
      />

      {/* Product detail modal */}
      <PartDetailModal
        part={selectedPart}
        onClose={() => setSelectedPart(null)}
      />
    </div>
  );
}
