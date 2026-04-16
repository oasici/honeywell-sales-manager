import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Link } from 'react-router-dom';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/ui/DataTable';
import { Skeleton } from '../../components/ui/Skeleton';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { complianceApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';

import type { ConsentStatus } from '../../lib/types';

interface RetentionReport {
  overdue_count: number;
  customers: { id: number; name: string; retention_until: string }[];
}

export default function ComplianceDashboardPage() {
  const queryClient = useQueryClient();

  const [customerIdInput, setCustomerIdInput] = useState('');
  const [searchedCustomerId, setSearchedCustomerId] = useState<number | null>(null);
  const [isAnonymizeOpen, setIsAnonymizeOpen] = useState(false);

  const consentQuery = useQuery<ConsentStatus>({
    queryKey: ['compliance', 'consent', searchedCustomerId],
    queryFn: () => complianceApi.getConsent(searchedCustomerId!),
    enabled: searchedCustomerId !== null,
  });

  const retentionReportQuery = useQuery<RetentionReport>({
    queryKey: ['compliance', 'retentionReport'],
    queryFn: () => complianceApi.getRetentionReport(),
  });

  const recordConsentMutation = useMutation({
    mutationFn: () =>
      complianceApi.recordConsent(searchedCustomerId!, {
        consent: true,
        method: 'manual',
        purpose: 'general',
      }),
    onSuccess: () => {
      toast.success('Onay basariyla kaydedildi');
      queryClient.invalidateQueries({ queryKey: ['compliance', 'consent', searchedCustomerId] });
    },
    onError: () => toast.error('Onay kaydedilemedi'),
  });

  const exportDataMutation = useMutation({
    mutationFn: () => complianceApi.exportData(searchedCustomerId!),
    onSuccess: () => toast.success('Veri aktarimi baslatildi'),
    onError: () => toast.error('Veri aktarimi basarisiz'),
  });

  const anonymizeDataMutation = useMutation({
    mutationFn: () => complianceApi.anonymizeData(searchedCustomerId!),
    onSuccess: () => {
      toast.success('Veri anonimlestirildi');
      setIsAnonymizeOpen(false);
      queryClient.invalidateQueries({ queryKey: ['compliance', 'consent', searchedCustomerId] });
    },
    onError: () => {
      toast.error('Anonimlestime basarisiz');
      setIsAnonymizeOpen(false);
    },
  });

  function handleSearch() {
    const parsed = parseInt(customerIdInput, 10);
    if (isNaN(parsed) || parsed <= 0) {
      toast.error('Gecerli bir musteri ID giriniz');
      return;
    }
    setSearchedCustomerId(parsed);
  }

  const consent = consentQuery.data;
  const report = retentionReportQuery.data;
  const overdueCount = report?.overdue_count ?? 0;

  const retentionColumns = [
    { key: 'id', header: 'Musteri ID', sortable: true },
    { key: 'name', header: 'Musteri Adi', sortable: true },
    {
      key: 'retention_until',
      header: 'Saklama Tarihi',
      render: (row: { id: number; name: string; retention_until: string }) => (
        <span className="text-sm text-gray-500">{formatDateTime(row.retention_until)}</span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Uyumluluk Paneli"
        description="KVKK ve veri koruma uyumluluk yonetimi"
      />

      {/* Search */}
      <div className="mb-6 flex items-end gap-3">
        <div className="max-w-xs flex-1">
          <Input
            label="Musteri ID"
            placeholder="Musteri ID giriniz"
            value={customerIdInput}
            onChange={(e) => setCustomerIdInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSearch();
            }}
          />
        </div>
        <Button onClick={handleSearch}>Ara</Button>
      </div>

      {/* Consent status */}
      {consentQuery.isLoading && <Skeleton variant="card" />}

      {consent && (
        <Card title="Onay Durumu" className="mb-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div>
              <p className="text-xs font-medium text-gray-500">Onay Durumu</p>
              <Badge variant={consent.has_consent ? 'success' : 'danger'}>
                {consent.has_consent ? 'Onay Var' : 'Onay Yok'}
              </Badge>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500">Onay Tarihi</p>
              <p className="text-sm text-gray-900">
                {consent.consent_date ? formatDateTime(consent.consent_date) : '-'}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500">Yontem</p>
              <p className="text-sm text-gray-900">{consent.method ?? '-'}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500">Amac</p>
              <p className="text-sm text-gray-900">{consent.purpose ?? '-'}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-gray-500">Saklama Bitis</p>
              <p className="text-sm text-gray-900">
                {consent.retention_until ? formatDateTime(consent.retention_until) : '-'}
              </p>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2">
            <Button
              onClick={() => recordConsentMutation.mutate()}
              loading={recordConsentMutation.isPending}
            >
              Onay Kaydet
            </Button>
            <Button
              variant="secondary"
              onClick={() => exportDataMutation.mutate()}
              loading={exportDataMutation.isPending}
              disabled={!searchedCustomerId}
            >
              Veriyi Aktar
            </Button>
            <Button
              variant="danger"
              onClick={() => setIsAnonymizeOpen(true)}
              disabled={!searchedCustomerId}
            >
              Anonimlesitir
            </Button>
          </div>
        </Card>
      )}

      {/* Retention report */}
      <Card
        title="Saklama Suresi Raporu"
        action={
          <Badge variant={overdueCount > 0 ? 'danger' : 'success'}>
            {overdueCount} gecikme
          </Badge>
        }
        className="mb-6"
      >
        {retentionReportQuery.isLoading && <Skeleton variant="table" />}

        {!retentionReportQuery.isLoading && (
          <DataTable
            columns={retentionColumns}
            data={report?.customers ?? []}
            emptyMessage="Gecikme bulunamadi"
          />
        )}
      </Card>

      {/* Navigation links */}
      <div className="flex gap-3">
        <Link
          to="/compliance/retention"
          className="text-sm font-medium text-honeywell-red hover:underline"
        >
          Saklama Politikalari
        </Link>
        <Link
          to="/compliance/breaches"
          className="text-sm font-medium text-honeywell-red hover:underline"
        >
          Ihlal Bildirimleri
        </Link>
      </div>

      <ConfirmDialog
        isOpen={isAnonymizeOpen}
        onClose={() => setIsAnonymizeOpen(false)}
        onConfirm={() => anonymizeDataMutation.mutate()}
        title="Veriyi Anonimletir"
        message="Bu musteri verisi kalici olarak anonimlestirilecektir. Devam etmek istediginizden emin misiniz?"
        confirmLabel="Anonimlesitir"
        confirmVariant="danger"
        isLoading={anonymizeDataMutation.isPending}
      />
    </div>
  );
}
