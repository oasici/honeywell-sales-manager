import { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { DataTable } from '../../components/ui/DataTable';
import { Badge } from '../../components/ui/Badge';
import { partsApi } from '../../lib/api';
import type { SparePart, PaginatedResponse } from '../../lib/types';

export default function PartsPage() {
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
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

  interface PartsImportResponse {
    imported: number;
    parts_created?: number;
    parts_updated?: number;
    prices_created?: number;
  }

  const importMutation = useMutation<PartsImportResponse, Error, File>({
    mutationFn: (file: File) => partsApi.importParts(file) as Promise<PartsImportResponse>,
    onSuccess: (res) => {
      const parts = (res.parts_created || 0) + (res.parts_updated || 0);
      const prices = res.prices_created || 0;
      toast.success(
        `${parts} parca (${res.parts_created || 0} yeni, ${res.parts_updated || 0} guncellendi)` +
        (prices > 0 ? ` ve ${prices} fiyat ice aktarildi` : ' ice aktarildi')
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

  const categoryOptions = [
    { value: '', label: 'Tum Kategoriler' },
    ...(categories || []).map((c) => ({ value: c, label: c })),
  ];

  const columns = [
    {
      key: 'honeywell_code',
      header: 'Honeywell Kodu',
      sortable: true,
      render: (row: SparePart) => (
        <span className="font-mono text-sm font-semibold text-gray-900">
          {row.honeywell_code}
        </span>
      ),
    },
    {
      key: 'name_tr',
      header: 'Isim (TR)',
      render: (row: SparePart) => (
        <span className="text-sm">{row.name_tr || '-'}</span>
      ),
    },
    {
      key: 'name_en',
      header: 'Isim (EN)',
      render: (row: SparePart) => (
        <span className="text-sm">{row.name_en || '-'}</span>
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
      key: 'has_price',
      header: 'Fiyat Durumu',
      render: (row: SparePart) =>
        row.has_price ? (
          <Badge variant="success">Fiyatli</Badge>
        ) : (
          <Badge variant="warning">Fiyatsiz</Badge>
        ),
    },
    {
      key: 'is_active',
      header: 'Durum',
      render: (row: SparePart) =>
        row.is_active ? (
          <Badge variant="success">Aktif</Badge>
        ) : (
          <Badge variant="default">Pasif</Badge>
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
          accept=".xlsx,.xls,.csv"
          className="hidden"
        />
        <Button
          loading={importMutation.isPending}
          onClick={() => fileRef.current?.click()}
        >
          Excel / CSV Yukle
        </Button>
      </PageHeader>

      {/* Info banner */}
      <div className="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
        <strong>Excel Formatı:</strong> honeywell_code (zorunlu), name_tr, name_en, category, list_price, discount_pct, currency sütunlarını içeren tek bir dosya yükleyin. Parça ve fiyat bilgileri otomatik okunur.
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
      />
    </div>
  );
}
