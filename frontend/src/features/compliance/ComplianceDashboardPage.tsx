import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Link } from 'react-router-dom';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/ui/DataTable';
import { Skeleton } from '../../components/ui/Skeleton';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { complianceApi, customersApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import { useT } from '../../hooks/useT';

import type { ConsentStatus } from '../../lib/types';

interface RetentionReport {
  overdue_count: number;
  customers: { id: number; name: string; retention_until: string }[];
}

interface CustomerOption {
  id: number;
  name: string;
  company?: string;
  email?: string;
}

export default function ComplianceDashboardPage() {
  const t = useT();
  const queryClient = useQueryClient();

  const [customerIdInput, setCustomerIdInput] = useState('');
  const [searchedCustomerId, setSearchedCustomerId] = useState<number | null>(null);
  const [isAnonymizeOpen, setIsAnonymizeOpen] = useState(false);

  // V9 UAT #28: replace manual ID input with a customer dropdown so
  // the user picks from existing customers instead of typing an ID.
  const customersQuery = useQuery<{ items: CustomerOption[] }>({
    queryKey: ['compliance', 'customer-options'],
    queryFn: () =>
      customersApi.getCustomers({ page: 1, page_size: 200 }) as Promise<{
        items: CustomerOption[];
      }>,
  });
  const customerOptions: CustomerOption[] = customersQuery.data?.items ?? [];

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
      toast.success('Onay başarıyla kaydedildi');
      queryClient.invalidateQueries({ queryKey: ['compliance', 'consent', searchedCustomerId] });
    },
    onError: () => toast.error('Onay kaydedilemedi'),
  });

  const exportDataMutation = useMutation({
    mutationFn: () => complianceApi.exportData(searchedCustomerId!),
    onSuccess: () => toast.success('Veri aktarımı başlatıldı'),
    onError: () => toast.error('Veri aktarımı başarısız'),
  });

  const anonymizeDataMutation = useMutation({
    mutationFn: () => complianceApi.anonymizeData(searchedCustomerId!),
    onSuccess: () => {
      toast.success('Veri anonimleştirildi');
      setIsAnonymizeOpen(false);
      queryClient.invalidateQueries({ queryKey: ['compliance', 'consent', searchedCustomerId] });
    },
    onError: () => {
      toast.error('Anonimleştirme başarısız');
      setIsAnonymizeOpen(false);
    },
  });

  function handleSearch() {
    const parsed = parseInt(customerIdInput, 10);
    if (isNaN(parsed) || parsed <= 0) {
      toast.error('Geçerli bir müşteri ID giriniz');
      return;
    }
    setSearchedCustomerId(parsed);
  }

  const consent = consentQuery.data;
  const report = retentionReportQuery.data;
  const overdueCount = report?.overdue_count ?? 0;

  const retentionColumns = [
    { key: 'id', header: 'Müşteri ID', sortable: true },
    { key: 'name', header: 'Müşteri Adı', sortable: true },
    {
      key: 'retention_until',
      header: 'Saklama Tarihi',
      render: (row: { id: number; name: string; retention_until: string }) => (
        <span className="text-sm text-slate-500">{formatDateTime(row.retention_until)}</span>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Uyumluluk Paneli"
        description="KVKK ve veri koruma uyumluluk yönetimi"
      />

      {/* Search */}
      <div className="mb-6 flex items-end gap-3">
        <div className="max-w-md flex-1">
          <label className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300">
            Müşteri Seçin
          </label>
          <select
            value={customerIdInput}
            onChange={(e) => setCustomerIdInput(e.target.value)}
            className="w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
          >
            <option value="">— Müşteri seçin —</option>
            {customerOptions.map((c) => (
              <option key={c.id} value={String(c.id)}>
                #{c.id} — {c.name}
                {c.company && c.company !== c.name ? ` (${c.company})` : ''}
              </option>
            ))}
          </select>
          {customersQuery.isLoading && (
            <p className="mt-1 text-[11px] text-slate-500">{t('common.loading')}</p>
          )}
        </div>
        <Button onClick={handleSearch} disabled={!customerIdInput}>
          Ara
        </Button>
      </div>

      {/* Consent status */}
      {consentQuery.isLoading && <Skeleton variant="card" />}

      {consent && (
        <Card title="Onay Durumu" className="mb-6">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
            <div>
              <p className="text-xs font-medium text-slate-500">Onay Durumu</p>
              <Badge variant={consent.has_consent ? 'success' : 'danger'}>
                {consent.has_consent ? 'Onay Var' : 'Onay Yok'}
              </Badge>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Onay Tarihi</p>
              <p className="text-sm text-slate-900">
                {consent.consent_date ? formatDateTime(consent.consent_date) : '-'}
              </p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Yöntem</p>
              <p className="text-sm text-slate-900">{consent.method ?? '-'}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Amaç</p>
              <p className="text-sm text-slate-900">{consent.purpose ?? '-'}</p>
            </div>
            <div>
              <p className="text-xs font-medium text-slate-500">Saklama Bitişi</p>
              <p className="text-sm text-slate-900">
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
              Anonimleştir
            </Button>
          </div>
        </Card>
      )}

      {/* Retention report */}
      <Card
        title="Saklama Süresi Raporu"
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
            emptyMessage="Gecikme bulunamadı"
          />
        )}
      </Card>

      {/* Tab-style navigation to retention + breach surfaces (V9 UAT #28) */}
      <div className="flex gap-1 rounded-lg border border-slate-200 bg-slate-50 p-1 dark:border-slate-800 dark:bg-slate-900/40">
        <Link
          to="/compliance/retention"
          className="flex-1 rounded-md px-4 py-2 text-center text-sm font-medium text-slate-600 transition-colors hover:bg-white hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
        >
          Saklama Politikaları
        </Link>
        <Link
          to="/compliance/breaches"
          className="flex-1 rounded-md px-4 py-2 text-center text-sm font-medium text-slate-600 transition-colors hover:bg-white hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
        >
          İhlal Bildirimleri
        </Link>
      </div>

      <ConfirmDialog
        isOpen={isAnonymizeOpen}
        onClose={() => setIsAnonymizeOpen(false)}
        onConfirm={() => anonymizeDataMutation.mutate()}
        title="Veriyi Anonimleştir"
        message="Bu müşteri verisi kalıcı olarak anonimleştirilecektir. Devam etmek istediğinizden emin misiniz?"
        confirmLabel="Anonimleştir"
        confirmVariant="danger"
        isLoading={anonymizeDataMutation.isPending}
      />
    </div>
  );
}
