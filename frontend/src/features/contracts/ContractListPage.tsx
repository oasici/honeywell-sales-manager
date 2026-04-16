import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { contractsApi, customersApi } from '../../lib/api';
import type { Contract, Customer } from '../../lib/types';

const STATUS_OPTIONS = [
  { value: '', label: 'Tumu' },
  { value: 'draft', label: 'Taslak' },
  { value: 'active', label: 'Aktif' },
  { value: 'amended', label: 'Degistirilmis' },
  { value: 'expired', label: 'Suresi Dolmus' },
  { value: 'terminated', label: 'Feshedilmis' },
];

const STATUS_BADGES: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-700',
  active: 'bg-green-100 text-green-700',
  amended: 'bg-yellow-100 text-yellow-700',
  expired: 'bg-red-100 text-red-700',
  terminated: 'bg-red-200 text-red-800',
};

const STATUS_LABELS: Record<string, string> = {
  draft: 'Taslak',
  active: 'Aktif',
  amended: 'Degistirilmis',
  expired: 'Suresi Dolmus',
  terminated: 'Feshedilmis',
};

export default function ContractListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState('');
  const [search, setSearch] = useState('');
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'all' | 'expiring'>('all');

  // Create form state
  const [formTitle, setFormTitle] = useState('');
  const [formCustomerId, setFormCustomerId] = useState<number | null>(null);
  const [formCustomerSearch, setFormCustomerSearch] = useState('');
  const [formStartDate, setFormStartDate] = useState('');
  const [formEndDate, setFormEndDate] = useState('');
  const [formValue, setFormValue] = useState('');

  const { data: contractsData, isLoading } = useQuery({
    queryKey: ['contracts', statusFilter, search],
    queryFn: () =>
      contractsApi.list({
        ...(statusFilter ? { status: statusFilter } : {}),
        ...(search ? { search } : {}),
      }),
  });

  const { data: expiringData } = useQuery({
    queryKey: ['contracts-expiring'],
    queryFn: () => contractsApi.expiring(30),
  });

  const { data: customerResults } = useQuery<{ items: Customer[] }>({
    queryKey: ['customers-search', formCustomerSearch],
    queryFn: () => customersApi.getCustomers({ search: formCustomerSearch, page_size: 10 }),
    enabled: formCustomerSearch.length >= 2,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => contractsApi.create(payload),
    onSuccess: (data) => {
      toast.success('Kontrat olusturuldu');
      queryClient.invalidateQueries({ queryKey: ['contracts'] });
      setIsCreateOpen(false);
      resetForm();
      navigate(`/contracts/${(data as Contract).id}`);
    },
    onError: () => toast.error('Kontrat olusturulamadi'),
  });

  const resetForm = useCallback(() => {
    setFormTitle('');
    setFormCustomerId(null);
    setFormCustomerSearch('');
    setFormStartDate('');
    setFormEndDate('');
    setFormValue('');
  }, []);

  const handleCreate = useCallback(() => {
    if (!formTitle || !formCustomerId) {
      toast.error('Baslik ve musteri zorunludur');
      return;
    }
    createMutation.mutate({
      customer_id: formCustomerId,
      title: formTitle,
      start_date: formStartDate || undefined,
      end_date: formEndDate || undefined,
      value: formValue ? parseFloat(formValue) : undefined,
    });
  }, [formTitle, formCustomerId, formStartDate, formEndDate, formValue, createMutation]);

  const contracts: Contract[] = contractsData?.contracts || [];
  const expiringContracts: Contract[] = expiringData?.contracts || [];
  const expiringCount = expiringData?.count || 0;

  return (
    <div>
      <PageHeader title="Kontratlar" description="Kontrat yasam dongusu yonetimi">
        <Button onClick={() => setIsCreateOpen(true)}>Yeni Kontrat</Button>
      </PageHeader>

      {/* Tabs */}
      <div className="mb-4 flex gap-2">
        <button
          type="button"
          onClick={() => setActiveTab('all')}
          className={`rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'all'
              ? 'bg-honeywell-red text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Tum Kontratlar
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('expiring')}
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
            activeTab === 'expiring'
              ? 'bg-honeywell-red text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          }`}
        >
          Suresi Dolan
          {expiringCount > 0 && (
            <span
              className={`flex h-5 min-w-[20px] items-center justify-center rounded-full px-1.5 text-[10px] font-bold ${
                activeTab === 'expiring'
                  ? 'bg-white text-honeywell-red'
                  : 'bg-honeywell-red text-white'
              }`}
            >
              {expiringCount}
            </span>
          )}
        </button>
      </div>

      {activeTab === 'all' && (
        <>
          {/* Filters */}
          <div className="mb-4 flex flex-wrap gap-3">
            <div className="w-48">
              <Select
                label="Durum"
                options={STATUS_OPTIONS}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
              />
            </div>
            <div className="w-64">
              <Input
                label="Ara"
                placeholder="Kontrat basligi..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>

          {isLoading && <Skeleton variant="card" count={3} />}

          {!isLoading && contracts.length === 0 && (
            <Card>
              <p className="py-8 text-center text-sm text-gray-500">Kontrat bulunamadi</p>
            </Card>
          )}

          {!isLoading && contracts.length > 0 && (
            <Card>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50">
                      <th className="px-3 py-2 text-xs font-semibold text-gray-500">Baslik</th>
                      <th className="px-3 py-2 text-xs font-semibold text-gray-500">Durum</th>
                      <th className="px-3 py-2 text-xs font-semibold text-gray-500">Baslangic</th>
                      <th className="px-3 py-2 text-xs font-semibold text-gray-500">Bitis</th>
                      <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                        Deger
                      </th>
                      <th className="px-3 py-2 text-xs font-semibold text-gray-500">Olusturulma</th>
                    </tr>
                  </thead>
                  <tbody>
                    {contracts.map((contract) => (
                      <tr
                        key={contract.id}
                        onClick={() => navigate(`/contracts/${contract.id}`)}
                        className="cursor-pointer border-b border-gray-100 hover:bg-gray-50 transition-colors"
                      >
                        <td className="px-3 py-2 font-medium text-gray-900">{contract.title}</td>
                        <td className="px-3 py-2">
                          <span
                            className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_BADGES[contract.status] || 'bg-gray-100 text-gray-700'}`}
                          >
                            {STATUS_LABELS[contract.status] || contract.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-gray-600">{contract.start_date || '-'}</td>
                        <td className="px-3 py-2 text-gray-600">{contract.end_date || '-'}</td>
                        <td className="px-3 py-2 text-right font-medium text-gray-900">
                          {contract.value != null
                            ? contract.value.toLocaleString('tr-TR', { minimumFractionDigits: 2 })
                            : '-'}
                        </td>
                        <td className="px-3 py-2 text-xs text-gray-400">
                          {contract.created_at
                            ? new Date(contract.created_at).toLocaleDateString('tr-TR')
                            : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </>
      )}

      {activeTab === 'expiring' && (
        <Card title="Suresi Yaklasiyor (30 gun)">
          {expiringContracts.length === 0 ? (
            <p className="py-8 text-center text-sm text-gray-500">
              Suresi dolmak uzere olan kontrat yok
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-gray-200 bg-gray-50">
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500">Baslik</th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500">Bitis Tarihi</th>
                    <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                      Deger
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {expiringContracts.map((contract) => (
                    <tr
                      key={contract.id}
                      onClick={() => navigate(`/contracts/${contract.id}`)}
                      className="cursor-pointer border-b border-gray-100 hover:bg-gray-50 transition-colors"
                    >
                      <td className="px-3 py-2 font-medium text-gray-900">{contract.title}</td>
                      <td className="px-3 py-2 text-red-600 font-medium">
                        {contract.end_date || '-'}
                      </td>
                      <td className="px-3 py-2 text-right font-medium text-gray-900">
                        {contract.value != null
                          ? contract.value.toLocaleString('tr-TR', { minimumFractionDigits: 2 })
                          : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* Create Modal */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-lg rounded-xl bg-white p-6 shadow-2xl">
            <h3 className="mb-4 text-lg font-semibold text-gray-900">Yeni Kontrat</h3>
            <div className="space-y-3">
              <Input
                label="Baslik"
                value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)}
                placeholder="Kontrat basligi"
              />
              <div className="relative">
                <Input
                  label="Musteri"
                  value={formCustomerSearch}
                  onChange={(e) => setFormCustomerSearch(e.target.value)}
                  placeholder="Musteri ara..."
                />
                {customerResults?.items &&
                  customerResults.items.length > 0 &&
                  formCustomerSearch.length >= 2 &&
                  !formCustomerId && (
                    <div className="absolute z-20 mt-1 w-full rounded-lg border border-gray-200 bg-white shadow-lg max-h-40 overflow-y-auto">
                      {customerResults.items.map((c) => (
                        <button
                          key={c.id}
                          type="button"
                          onClick={() => {
                            setFormCustomerId(c.id);
                            setFormCustomerSearch(c.company || c.name);
                          }}
                          className="w-full px-4 py-2 text-left text-sm hover:bg-gray-50"
                        >
                          <span className="font-medium">{c.company || c.name}</span>
                          <span className="ml-2 text-xs text-gray-400">{c.email}</span>
                        </button>
                      ))}
                    </div>
                  )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Input
                  label="Baslangic Tarihi"
                  type="date"
                  value={formStartDate}
                  onChange={(e) => setFormStartDate(e.target.value)}
                />
                <Input
                  label="Bitis Tarihi"
                  type="date"
                  value={formEndDate}
                  onChange={(e) => setFormEndDate(e.target.value)}
                />
              </div>
              <Input
                label="Deger"
                type="number"
                min={0}
                step={0.01}
                value={formValue}
                onChange={(e) => setFormValue(e.target.value)}
                placeholder="Kontrat degeri"
              />
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => {
                  setIsCreateOpen(false);
                  resetForm();
                }}
              >
                Iptal
              </Button>
              <Button onClick={handleCreate} loading={createMutation.isPending}>
                Olustur
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
