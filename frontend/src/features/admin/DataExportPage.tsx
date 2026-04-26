import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, AlertCircle } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Select } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { auditApi, usersApi } from '../../lib/api';

interface UserSummary {
  id: number;
  email: string;
  full_name?: string;
  role?: string;
  is_active?: boolean;
}

interface UsersListResponse {
  items?: UserSummary[];
  users?: UserSummary[];
}

interface ExportCounts {
  audit_events: number;
  created_customers: number;
  owned_opportunities: number;
  sent_emails: number;
}

interface UserDataExport {
  exported_at: string;
  exported_by: number;
  user: { id: number; email: string; full_name?: string };
  counts: ExportCounts;
  audit_events: unknown[];
  created_customers: unknown[];
  owned_opportunities: unknown[];
  sent_emails: unknown[];
}

function downloadJson(payload: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

export default function DataExportPage() {
  const [selectedUserId, setSelectedUserId] = useState<string>('');
  const [exporting, setExporting] = useState(false);
  const [lastExport, setLastExport] = useState<UserDataExport | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data: usersData, isLoading: usersLoading } = useQuery<UsersListResponse>({
    queryKey: ['users-for-export'],
    // Backend caps page_size at 100. If we ever need to handle more
    // users, paginate here instead of bumping the cap.
    queryFn: () => usersApi.getUsers({ page_size: 100 }),
  });

  const users = usersData?.items ?? usersData?.users ?? [];

  const userOptions = [
    { value: '', label: 'Kullanıcı seçin...' },
    ...users.map((u) => ({
      value: String(u.id),
      label: `${u.full_name ?? u.email} (#${u.id})`,
    })),
  ];

  const handleExport = async () => {
    if (!selectedUserId) return;
    setExporting(true);
    setErrorMsg(null);
    try {
      const userId = Number(selectedUserId);
      const payload = (await auditApi.exportUserData(userId)) as UserDataExport;
      setLastExport(payload);
      const stamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
      downloadJson(payload, `kvkk-data-export-user-${userId}-${stamp}.json`);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Bilinmeyen hata: dışa aktarma başarısız';
      setErrorMsg(message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="KVKK Veri Dışa Aktarma"
        description="Article 15 — Kullanıcının sistemdeki tüm kayıtlarını JSON olarak indir"
      />

      <div className="mb-6 rounded-lg border border-amber-200 bg-amber-50 p-4">
        <div className="flex gap-3">
          <AlertCircle size={20} className="flex-shrink-0 text-amber-600" />
          <div className="text-sm text-amber-900">
            <p className="font-medium">Bu işlem audit log'a kaydedilir.</p>
            <p className="mt-1">
              Dışa aktarmanın hangi kullanıcı için, hangi yönetici tarafından
              yapıldığı ve toplam kayıt sayısı KVKK officer tarafından
              denetlenebilir.
            </p>
          </div>
        </div>
      </div>

      <div className="mb-6 max-w-md">
        <Select
          label="Veri sahibi (kullanıcı)"
          options={userOptions}
          value={selectedUserId}
          onChange={(e) => {
            setSelectedUserId(e.target.value);
            setLastExport(null);
            setErrorMsg(null);
          }}
          disabled={usersLoading}
        />
      </div>

      <Button
        variant="primary"
        onClick={handleExport}
        disabled={!selectedUserId || exporting}
      >
        <Download size={16} className="mr-1.5" />
        {exporting ? 'Hazırlanıyor...' : 'JSON Olarak İndir'}
      </Button>

      {errorMsg && (
        <div className="mt-4 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {errorMsg}
        </div>
      )}

      {lastExport && (
        <div className="mt-8 rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h3 className="mb-3 text-sm font-semibold text-gray-900">
            Son dışa aktarma özeti
          </h3>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
            <dt className="text-gray-500">Kullanıcı</dt>
            <dd className="font-medium text-gray-900">
              {lastExport.user.full_name ?? lastExport.user.email} (#{lastExport.user.id})
            </dd>
            <dt className="text-gray-500">Audit olayları</dt>
            <dd className="text-gray-900">{lastExport.counts.audit_events}</dd>
            <dt className="text-gray-500">Oluşturduğu müşteriler</dt>
            <dd className="text-gray-900">{lastExport.counts.created_customers}</dd>
            <dt className="text-gray-500">Sahip olduğu fırsatlar</dt>
            <dd className="text-gray-900">{lastExport.counts.owned_opportunities}</dd>
            <dt className="text-gray-500">Email gönderimleri</dt>
            <dd className="text-gray-900">{lastExport.counts.sent_emails}</dd>
            <dt className="text-gray-500">Dışa aktarma zamanı</dt>
            <dd className="text-gray-900">
              {new Date(lastExport.exported_at).toLocaleString('tr-TR')}
            </dd>
          </dl>
        </div>
      )}
    </div>
  );
}
