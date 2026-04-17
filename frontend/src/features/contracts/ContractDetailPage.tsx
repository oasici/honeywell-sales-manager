import { useState, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { contractsApi } from '../../lib/api';
import type { Contract, ContractAmendment } from '../../lib/types';

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
  expired: 'Süresi Dolmus',
  terminated: 'Feshedilmis',
};

const AMENDMENT_TYPE_LABELS: Record<string, string> = {
  extension: 'Uzatma',
  modification: 'Degisiklik',
  termination: 'Fesih',
};

const AMENDMENT_TYPE_OPTIONS = [
  { value: 'extension', label: 'Uzatma' },
  { value: 'modification', label: 'Degisiklik' },
  { value: 'termination', label: 'Fesih' },
];

const STATUS_FLOW = ['draft', 'active', 'amended', 'expired'];

export default function ContractDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const contractId = Number(id);

  const [isAmendOpen, setIsAmendOpen] = useState(false);
  const [amendType, setAmendType] = useState('modification');
  const [amendChanges, setAmendChanges] = useState('');
  const [amendDate, setAmendDate] = useState('');

  const { data: contract, isLoading } = useQuery<Contract>({
    queryKey: ['contract', contractId],
    queryFn: () => contractsApi.get(contractId),
    enabled: !!contractId,
  });

  const activateMutation = useMutation({
    mutationFn: () => contractsApi.activate(contractId),
    onSuccess: () => {
      toast.success('Kontrat aktiflestirildi');
      queryClient.invalidateQueries({ queryKey: ['contract', contractId] });
    },
    onError: () => toast.error('Aktiflesitirme başarısız'),
  });

  const amendMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => contractsApi.amend(contractId, payload),
    onSuccess: () => {
      toast.success('Degisiklik eklendi');
      queryClient.invalidateQueries({ queryKey: ['contract', contractId] });
      setIsAmendOpen(false);
      setAmendType('modification');
      setAmendChanges('');
      setAmendDate('');
    },
    onError: () => toast.error('Degisiklik eklenemedi'),
  });

  const handleAmend = useCallback(() => {
    amendMutation.mutate({
      amendment_type: amendType,
      changes_json: amendChanges || undefined,
      effective_date: amendDate || undefined,
    });
  }, [amendType, amendChanges, amendDate, amendMutation]);

  if (isLoading) {
    return <Skeleton variant="card" count={3} />;
  }

  if (!contract) {
    return (
      <div className="py-16 text-center">
        <p className="text-sm text-gray-500">Kontrat bulunamadi</p>
        <Button variant="secondary" onClick={() => navigate('/contracts')} className="mt-4">
          Geri Don
        </Button>
      </div>
    );
  }

  const amendments: ContractAmendment[] = contract.amendments || [];

  return (
    <div>
      <PageHeader title={contract.title} description="Kontrat detaylari">
        <span
          className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-medium ${STATUS_BADGES[contract.status] || 'bg-gray-100 text-gray-700'}`}
        >
          {STATUS_LABELS[contract.status] || contract.status}
        </span>
        <Button variant="secondary" onClick={() => navigate('/contracts')}>
          Geri Don
        </Button>
        {contract.status === 'draft' && (
          <Button
            onClick={() => activateMutation.mutate()}
            loading={activateMutation.isPending}
            className="!bg-green-600 !text-white hover:!bg-green-700"
          >
            Aktifles
          </Button>
        )}
        <Button variant="secondary" onClick={() => setIsAmendOpen(true)}>
          Degisiklik Ekle
        </Button>
      </PageHeader>

      <div className="space-y-6">
        {/* Status Flow */}
        <Card title="Durum Akisi">
          <div className="flex items-center gap-1">
            {STATUS_FLOW.map((step, idx) => {
              const isCurrent = contract.status === step;
              const isPast = STATUS_FLOW.indexOf(contract.status) > idx;
              return (
                <div key={step} className="flex items-center gap-1">
                  {idx > 0 && (
                    <div className={`h-0.5 w-8 ${isPast ? 'bg-green-400' : 'bg-gray-200'}`} />
                  )}
                  <div
                    className={`flex items-center justify-center rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                      isCurrent
                        ? 'bg-honeywell-red text-white'
                        : isPast
                          ? 'bg-green-100 text-green-700'
                          : 'bg-gray-100 text-gray-400'
                    }`}
                  >
                    {STATUS_LABELS[step]}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        {/* Contract Info */}
        <Card title="Kontrat Bilgileri">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <p className="text-xs text-gray-500">Müşteri ID</p>
              <p className="text-sm font-medium text-gray-900">{contract.customer_id}</p>
            </div>
            {contract.quote_id && (
              <div>
                <p className="text-xs text-gray-500">Teklif ID</p>
                <p className="text-sm font-medium text-gray-900">{contract.quote_id}</p>
              </div>
            )}
            <div>
              <p className="text-xs text-gray-500">Baslangic Tarihi</p>
              <p className="text-sm font-medium text-gray-900">{contract.start_date || '-'}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Bitis Tarihi</p>
              <p className="text-sm font-medium text-gray-900">{contract.end_date || '-'}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500">Değer</p>
              <p className="text-sm font-medium text-gray-900">
                {contract.value != null
                  ? contract.value.toLocaleString('tr-TR', { minimumFractionDigits: 2 })
                  : '-'}
              </p>
            </div>
            {contract.signed_at && (
              <div>
                <p className="text-xs text-gray-500">Imzalanma</p>
                <p className="text-sm font-medium text-gray-900">
                  {new Date(contract.signed_at).toLocaleDateString('tr-TR')}
                  {contract.signed_by && (
                    <span className="text-gray-500"> - {contract.signed_by}</span>
                  )}
                </p>
              </div>
            )}
          </div>
        </Card>

        {/* Amendment Timeline */}
        <Card title="Degisiklik Gecmisi">
          {amendments.length === 0 ? (
            <p className="py-6 text-center text-sm text-gray-400">Henüz degisiklik yok</p>
          ) : (
            <div className="relative pl-6">
              <div className="absolute left-2 top-0 bottom-0 w-0.5 bg-gray-200" />
              <div className="space-y-4">
                {amendments.map((amendment) => (
                  <div key={amendment.id} className="relative">
                    <div className="absolute -left-4 top-1.5 h-3 w-3 rounded-full border-2 border-honeywell-red bg-white" />
                    <div className="rounded-lg border border-gray-100 bg-gray-50 p-3 ml-2">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold text-gray-700">
                          {AMENDMENT_TYPE_LABELS[amendment.amendment_type] ||
                            amendment.amendment_type}
                        </span>
                        {amendment.effective_date && (
                          <span className="text-xs text-gray-400">
                            Gecerlilik: {amendment.effective_date}
                          </span>
                        )}
                      </div>
                      {amendment.changes_json && (
                        <p className="mt-1 text-xs text-gray-600">{amendment.changes_json}</p>
                      )}
                      <p className="mt-1 text-[10px] text-gray-400">
                        {amendment.created_at
                          ? new Date(amendment.created_at).toLocaleDateString('tr-TR')
                          : ''}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      </div>

      {/* Amendment Modal */}
      {isAmendOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
            <h3 className="mb-4 text-lg font-semibold text-gray-900">Degisiklik Ekle</h3>
            <div className="space-y-3">
              <Select
                label="Degisiklik Tipi"
                options={AMENDMENT_TYPE_OPTIONS}
                value={amendType}
                onChange={(e) => setAmendType(e.target.value)}
              />
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">Açıklama</label>
                <textarea
                  className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-honeywell-light focus:border-honeywell-red"
                  rows={3}
                  value={amendChanges}
                  onChange={(e) => setAmendChanges(e.target.value)}
                  placeholder="Degisiklik detaylari..."
                />
              </div>
              <Input
                label="Gecerlilik Tarihi"
                type="date"
                value={amendDate}
                onChange={(e) => setAmendDate(e.target.value)}
              />
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setIsAmendOpen(false)}>
                İptal
              </Button>
              <Button onClick={handleAmend} loading={amendMutation.isPending}>
                Ekle
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
