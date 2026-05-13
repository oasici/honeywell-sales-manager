import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, AlertCircle, CheckCircle2 } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Select } from '../../components/ui/Select';
import { Button } from '../../components/ui/Button';
import { auditApi, usersApi } from '../../lib/api';
import { useT } from '../../hooks/useT';

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
  const t = useT();
  const [selectedUserId, setSelectedUserId] = useState<string>('');
  const [exporting, setExporting] = useState(false);
  const [lastExport, setLastExport] = useState<UserDataExport | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data: usersData, isLoading: usersLoading } = useQuery<UsersListResponse>({
    queryKey: ['users-for-export'],
    queryFn: () => usersApi.getUsers({ page_size: 100 }),
  });

  const users = usersData?.items ?? usersData?.users ?? [];

  const userOptions = [
    { value: '', label: t('common.select_user') },
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

  const summaryRows: Array<{ label: string; value: string }> = lastExport
    ? [
        {
          label: 'Kullanıcı',
          value: `${lastExport.user.full_name ?? lastExport.user.email} (#${lastExport.user.id})`,
        },
        { label: 'Audit olayları', value: String(lastExport.counts.audit_events) },
        { label: 'Oluşturduğu müşteriler', value: String(lastExport.counts.created_customers) },
        { label: 'Sahip olduğu fırsatlar', value: String(lastExport.counts.owned_opportunities) },
        { label: 'Email gönderimleri', value: String(lastExport.counts.sent_emails) },
        {
          label: 'Dışa aktarma zamanı',
          value: new Date(lastExport.exported_at).toLocaleString('tr-TR'),
        },
      ]
    : [];

  return (
    <div>
      <PageHeader
        title="KVKK Veri Dışa Aktarma"
        description="Article 15 — Kullanıcının sistemdeki tüm kayıtlarını JSON olarak indir"
      />

      {/* Audit warning callout — amber tint signals "you're being watched" */}
      <div className="mb-6 flex items-start gap-3 rounded-2xl border border-amber-100 bg-amber-50/70 p-4 dark:border-amber-900/40 dark:bg-amber-950/20">
        <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-amber-100 text-amber-700 ring-1 ring-inset ring-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:ring-amber-900/60">
          <AlertCircle size={16} />
        </span>
        <div className="min-w-0 flex-1 text-[13px] leading-5 text-amber-900 dark:text-amber-200">
          <p className="font-semibold">Bu işlem audit log'a kaydedilir.</p>
          <p className="mt-0.5 text-amber-800/90 dark:text-amber-300/80">
            Dışa aktarmanın hangi kullanıcı için, hangi yönetici tarafından yapıldığı ve toplam
            kayıt sayısı KVKK officer tarafından denetlenebilir.
          </p>
        </div>
      </div>

      <div className="mb-4 max-w-md">
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
        disabled={!selectedUserId}
        loading={exporting}
      >
        <Download size={14} />
        JSON Olarak İndir
      </Button>

      {errorMsg && (
        <div className="mt-4 rounded-2xl border border-red-100 bg-red-50/60 p-3.5 text-[13px] text-red-700 dark:border-red-900/40 dark:bg-red-950/20 dark:text-red-300">
          {errorMsg}
        </div>
      )}

      {lastExport && (
        <div className="mt-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center gap-2.5 border-b border-slate-100 px-5 py-4 dark:border-slate-800">
            <span className="inline-flex h-8 w-8 items-center justify-center rounded-[10px] bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-400 dark:ring-emerald-900/40">
              <CheckCircle2 size={14} />
            </span>
            <h3 className="text-[14px] font-semibold text-slate-900 dark:text-white">
              Son dışa aktarma özeti
            </h3>
          </div>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 px-5 py-4 text-[13px]">
            {summaryRows.map((row) => (
              <div key={row.label} className="contents">
                <dt className="text-slate-500 dark:text-slate-400">{row.label}</dt>
                <dd className="font-medium tabular-nums text-slate-900 dark:text-white">
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}
