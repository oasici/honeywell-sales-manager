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

  return (
    <Modal isOpen={!!part} onClose={onClose} title="Urun Detayi" size="lg">
      <div className="space-y-4">
        {/* Info highlight box */}
        {part.info && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            <span className="font-semibold">Bilgi: </span>
            {part.info}
          </div>
        )}

        <div className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
          <DetailField label="Honeywell Kodu" value={part.honeywell_code} />
          <DetailField label="Model No" value={part.model_number} />
          <DetailField label="Tanim (TR)" value={part.description_tr || part.name_tr} />
          <DetailField label="Tanim (EN)" value={part.description_en || part.name_en} />
          <DetailField label="Kategori" value={part.category} />
          <DetailField label="Alt Kategori" value={part.subcategory} />
          <DetailField
            label="T.P. (Transfer Price)"
            value={part.transfer_price != null ? `${formatPrice(part.transfer_price)} ${part.price_currency || ''}` : null}
            isHighlight={part.transfer_price != null}
          />
          <DetailField
            label="L.P. (List Price)"
            value={part.supplier_price != null ? `${formatPrice(part.supplier_price)} ${part.price_currency || ''}` : null}
            isHighlight={part.supplier_price != null}
          />
          <DetailField label="Olusturma Tarihi" value={part.created_at?.split('T')[0]} />
        </div>
      </div>
    </Modal>
  );
}

function DetailField({
  label,
  value,
  isHighlight = false,
}: {
  label: string;
  value: string | null | undefined;
  isHighlight?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs font-medium text-gray-500">{label}</dt>
      <dd className={`mt-0.5 ${isHighlight ? 'font-semibold text-gray-900' : 'text-gray-700'}`}>
        {value || '-'}
      </dd>
    </div>
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
        `${parts} parca (${res.parts_created || 0} yeni, ${res.parts_updated || 0} guncellendi)` +
        (res.skipped ? `, ${res.skipped} atlandi` : '') +
        ' ice aktarildi',
      );
      queryClient.invalidateQueries({ queryKey: ['parts'] });
      queryClient.invalidateQueries({ queryKey: ['parts-categories'] });
    },
    onError: () => toast.error('Katalog ice aktarimi basarisiz'),
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
    { value: '', label: 'Tum Kategoriler' },
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
      <PageHeader title="Yedek Parcalar" description="Honeywell yedek parca katalogu">
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
          Ice Aktar (Excel/CSV/PDF)
        </Button>
      </PageHeader>

      {/* Info banner */}
      <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
        <strong>Excel Formati:</strong> Model No / Honeywell Code (zorunlu), aciklama, transfer price,
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
        emptyMessage="Henuz parca bulunamadi"
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
