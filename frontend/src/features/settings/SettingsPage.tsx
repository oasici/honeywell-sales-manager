import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CheckCircle, AlertCircle, Trash2 } from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { settingsApi } from '../../lib/api';

interface SettingsData {
  quote_prefix: string;
  default_tax_rate: number;
  default_currency: string;
  quote_validity_days: number;
}

const CURRENCY_OPTIONS = [
  { value: 'TRY', label: 'TRY - Turk Lirasi' },
  { value: 'USD', label: 'USD - Amerikan Dolari' },
  { value: 'EUR', label: 'EUR - Euro' },
];

const DEFAULTS: SettingsData = {
  quote_prefix: 'HW',
  default_tax_rate: 20,
  default_currency: 'USD',
  quote_validity_days: 30,
};

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<SettingsData>(DEFAULTS);

  const { data: settings, isLoading } = useQuery<Record<string, unknown>>({
    queryKey: ['settings'],
    queryFn: settingsApi.getSettings,
  });

  useEffect(() => {
    if (settings) {
      const s = (settings as { settings?: Record<string, string> }).settings || settings;
      setForm({
        quote_prefix: (s.quote_prefix as string) || 'HW',
        default_tax_rate: Number(s.default_tax_rate) || 20,
        default_currency: (s.default_currency as string) || 'USD',
        quote_validity_days: Number(s.quote_validity_days) || 30,
      });
    }
  }, [settings]);

  const saveMutation = useMutation({
    mutationFn: (payload: SettingsData) =>
      settingsApi.updateSettings(payload as unknown as Record<string, unknown>),
    onSuccess: () => {
      toast.success('Ayarlar kaydedildi');
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
    onError: () => toast.error('Ayarlar kaydedilemedi'),
  });

  const updateField = (field: keyof SettingsData, value: string | number) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton variant="card" count={2} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Ayarlar" description="Sistem yapilandirmasi">
        <Button
          loading={saveMutation.isPending}
          onClick={() => saveMutation.mutate(form)}
        >
          Kaydet
        </Button>
      </PageHeader>

      <div className="space-y-6">
        {/* Email Settings - FIRST */}
        <EmailSettingsSection />

        {/* Quote Settings */}
        <Card title="Teklif Ayarlari">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Teklif On Eki"
              value={form.quote_prefix}
              onChange={(e) => updateField('quote_prefix', e.target.value)}
              placeholder="HW"
              helperText="Teklif numaralarinin basina eklenir (ornek: HW-2026-001)"
            />
            <Input
              label="Varsayilan KDV Orani (%)"
              type="number"
              min={0}
              max={100}
              value={form.default_tax_rate}
              onChange={(e) => updateField('default_tax_rate', Number(e.target.value))}
            />
            <Select
              label="Varsayilan Para Birimi"
              options={CURRENCY_OPTIONS}
              value={form.default_currency}
              onChange={(e) => updateField('default_currency', e.target.value)}
            />
            <Input
              label="Teklif Gecerlilik Suresi (gun)"
              type="number"
              min={1}
              value={form.quote_validity_days}
              onChange={(e) => updateField('quote_validity_days', Number(e.target.value))}
            />
          </div>
        </Card>
      </div>
    </div>
  );
}

/* ── Email Settings Section ── */
function EmailSettingsSection() {
  const queryClient = useQueryClient();

  const [emailForm, setEmailForm] = useState({
    email_address: '',
    email_password: '',
    imap_host: '',
    imap_port: 993,
    smtp_host: '',
    smtp_port: 587,
  });
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [editingServer, setEditingServer] = useState(false);

  const { data: creds, isLoading } = useQuery({
    queryKey: ['email-credentials'],
    queryFn: settingsApi.getEmailCredentials,
  });

  // Load stored credentials into form
  useEffect(() => {
    if (creds && creds.is_configured) {
      setEmailForm({
        email_address: creds.email_address || '',
        email_password: '',
        imap_host: creds.imap_host || '',
        imap_port: creds.imap_port || 993,
        smtp_host: creds.smtp_host || '',
        smtp_port: creds.smtp_port || 587,
      });
    }
  }, [creds]);

  // Auto-detect IMAP/SMTP when email changes
  const handleEmailChange = (email: string) => {
    setEmailForm((prev) => {
      const updated = { ...prev, email_address: email };

      // Auto-detect provider settings from domain
      const domain = email.includes('@') ? email.split('@')[1]?.toLowerCase() : '';
      if (domain) {
        const providers: Record<string, [string, number, string, number]> = {
          'gmail.com': ['imap.gmail.com', 993, 'smtp.gmail.com', 587],
          'googlemail.com': ['imap.gmail.com', 993, 'smtp.gmail.com', 587],
          'yahoo.com': ['imap.mail.yahoo.com', 993, 'smtp.mail.yahoo.com', 587],
          'yahoo.com.tr': ['imap.mail.yahoo.com', 993, 'smtp.mail.yahoo.com', 587],
          'outlook.com': ['outlook.office365.com', 993, 'smtp.office365.com', 587],
          'hotmail.com': ['outlook.office365.com', 993, 'smtp.office365.com', 587],
          'live.com': ['outlook.office365.com', 993, 'smtp.office365.com', 587],
          'yandex.com': ['imap.yandex.com', 993, 'smtp.yandex.com', 587],
          'icloud.com': ['imap.mail.me.com', 993, 'smtp.mail.me.com', 587],
        };
        const match = providers[domain];
        if (match) {
          updated.imap_host = match[0];
          updated.imap_port = match[1];
          updated.smtp_host = match[2];
          updated.smtp_port = match[3];
        } else {
          // Corporate default
          updated.imap_host = 'outlook.office365.com';
          updated.imap_port = 993;
          updated.smtp_host = 'smtp.office365.com';
          updated.smtp_port = 587;
        }
      }

      return updated;
    });
    setTestResult(null);
  };

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = { ...emailForm };
      if (!payload.email_password && creds?.is_configured) {
        payload.email_password = '___KEEP_EXISTING___';
      }
      return settingsApi.saveEmailCredentials(payload);
    },
    onSuccess: () => {
      toast.success('Email ayarlari kaydedildi');
      queryClient.invalidateQueries({ queryKey: ['email-credentials'] });
    },
    onError: () => toast.error('Email ayarlari kaydedilemedi'),
  });

  const testMutation = useMutation({
    mutationFn: () =>
      settingsApi.testEmailConnection(
        emailForm.email_password
          ? {
              email_address: emailForm.email_address,
              email_password: emailForm.email_password,
              imap_host: emailForm.imap_host || undefined,
              imap_port: emailForm.imap_port || undefined,
            }
          : undefined,
      ),
    onSuccess: (result) => {
      setTestResult(result);
      if (result.success) toast.success(result.message);
      else toast.error(result.message);
    },
    onError: () => {
      setTestResult({ success: false, message: 'Baglanti testi basarisiz' });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () =>
      settingsApi.updateSettings({
        email_address: '',
        email_password: '',
        imap_host: '',
        imap_port: '',
        smtp_host: '',
        smtp_port: '',
      }),
    onSuccess: () => {
      toast.success('Email baglantisi silindi');
      setEmailForm({
        email_address: '',
        email_password: '',
        imap_host: '',
        imap_port: 993,
        smtp_host: '',
        smtp_port: 587,
      });
      setTestResult(null);
      setShowDeleteConfirm(false);
      queryClient.invalidateQueries({ queryKey: ['email-credentials'] });
    },
    onError: () => toast.error('Email baglantisi silinemedi'),
  });

  if (isLoading) return <Skeleton variant="card" />;

  const isConfigured = creds?.is_configured;
  const canSave = emailForm.email_address.length > 3 && (emailForm.email_password.length > 0 || isConfigured);

  return (
    <>
      <Card title="Email Ayarlari">
        <div className="space-y-4">
          {/* Connection status */}
          {isConfigured && (
            <div className="flex items-center justify-between rounded-lg bg-green-50 border border-green-200 p-3">
              <div className="flex items-center gap-2 text-sm text-green-700">
                <CheckCircle size={16} className="shrink-0" />
                <span>
                  Bagli: <strong>{creds.email_address}</strong> ({creds.imap_host})
                </span>
              </div>
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-red-600 hover:bg-red-50 transition-colors"
              >
                <Trash2 size={14} />
                Baglantiyi Sil
              </button>
            </div>
          )}

          {/* Email + Password */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Email Adresi"
              type="email"
              value={emailForm.email_address}
              onChange={(e) => handleEmailChange(e.target.value)}
              placeholder="ornek@sirket.com"
            />
            <Input
              label="Email Sifresi / App Password"
              type="password"
              value={emailForm.email_password}
              onChange={(e) => {
                setEmailForm((p) => ({ ...p, email_password: e.target.value }));
                setTestResult(null);
              }}
              placeholder={isConfigured ? '(degistirmek icin yeni sifre girin)' : 'Sifre veya App Password'}
            />
          </div>

          {/* IMAP/SMTP info */}
          {emailForm.imap_host && !editingServer && (
            <div>
              <div className="grid grid-cols-2 gap-4 rounded-lg border border-gray-200 bg-gray-50 p-4 sm:grid-cols-4">
                <div>
                  <span className="text-xs font-medium text-gray-500">IMAP</span>
                  <p className="text-sm text-gray-800 font-mono">{emailForm.imap_host}</p>
                </div>
                <div>
                  <span className="text-xs font-medium text-gray-500">IMAP Port</span>
                  <p className="text-sm text-gray-800 font-mono">{emailForm.imap_port}</p>
                </div>
                <div>
                  <span className="text-xs font-medium text-gray-500">SMTP</span>
                  <p className="text-sm text-gray-800 font-mono">{emailForm.smtp_host}</p>
                </div>
                <div>
                  <span className="text-xs font-medium text-gray-500">SMTP Port</span>
                  <p className="text-sm text-gray-800 font-mono">{emailForm.smtp_port}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setEditingServer(true)}
                className="mt-2 text-xs text-gray-500 hover:text-honeywell-red transition-colors"
              >
                Sunucu ayarlarini duzenle
              </button>
            </div>
          )}

          {/* Editable IMAP/SMTP fields */}
          {editingServer && (
            <div>
              <div className="grid grid-cols-1 gap-4 rounded-lg border border-honeywell-light bg-red-50/30 p-4 sm:grid-cols-2">
                <Input
                  label="IMAP Sunucusu"
                  value={emailForm.imap_host}
                  onChange={(e) => setEmailForm((p) => ({ ...p, imap_host: e.target.value }))}
                />
                <Input
                  label="IMAP Port"
                  type="number"
                  value={String(emailForm.imap_port)}
                  onChange={(e) => setEmailForm((p) => ({ ...p, imap_port: Number(e.target.value) }))}
                />
                <Input
                  label="SMTP Sunucusu"
                  value={emailForm.smtp_host}
                  onChange={(e) => setEmailForm((p) => ({ ...p, smtp_host: e.target.value }))}
                />
                <Input
                  label="SMTP Port"
                  type="number"
                  value={String(emailForm.smtp_port)}
                  onChange={(e) => setEmailForm((p) => ({ ...p, smtp_port: Number(e.target.value) }))}
                />
              </div>
              <button
                type="button"
                onClick={() => setEditingServer(false)}
                className="mt-2 text-xs text-gray-500 hover:text-honeywell-red transition-colors"
              >
                Duzenlemeyi kapat
              </button>
            </div>
          )}

          {/* Test result */}
          {testResult && (
            <div
              className={`flex items-center gap-2 rounded-lg p-3 text-sm ${
                testResult.success
                  ? 'bg-green-50 border border-green-200 text-green-700'
                  : 'bg-red-50 border border-red-200 text-red-700'
              }`}
            >
              {testResult.success ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
              {testResult.message}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between pt-2">
            <Button
              variant="secondary"
              onClick={() => testMutation.mutate()}
              loading={testMutation.isPending}
              disabled={!canSave}
            >
              Baglantiyi Test Et
            </Button>
            <Button
              onClick={() => saveMutation.mutate()}
              loading={saveMutation.isPending}
              disabled={!canSave}
            >
              Email Ayarlarini Kaydet
            </Button>
          </div>
        </div>
      </Card>

      {/* Delete confirmation */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={() => deleteMutation.mutate()}
        title="Email Baglantisini Sil"
        message="Email baglantisi silinecek ve tum email ayarlari sifirlanacak. Bu islem geri alinamaz. Devam etmek istiyor musunuz?"
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </>
  );
}
