import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  CheckCircle,
  AlertCircle,
  Trash2,
  Sun,
  Moon,
  Minus,
  Plus,
  RotateCcw,
  Save,
  Bell,
  Copy,
  Calendar,
  Link2,
} from 'lucide-react';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { settingsApi, meetingsApi } from '../../lib/api';
import { usePreferencesStore } from '../../stores/preferencesStore';
import { useAuthStore } from '../../stores/authStore';
import { useT } from '../../hooks/useT';
import { LANGUAGE_OPTIONS } from '../../lib/i18n';
import SharingRulesSection from './SharingRulesSection';
import WebhookSettings from './WebhookSettings';

import type { StageConfig, MeetingLink, MeetingBooking } from '../../lib/types';

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
  const user = useAuthStore((state) => state.user);
  const [form, setForm] = useState<SettingsData>(DEFAULTS);

  const { data: settings, isLoading } = useQuery<Record<string, unknown>>({
    queryKey: ['settings'],
    queryFn: settingsApi.getSettings,
  });

  useEffect(() => {
    if (settings) {
      const s = (settings as { settings?: Record<string, string> }).settings || settings;
      queueMicrotask(() =>
        setForm({
          quote_prefix: (s.quote_prefix as string) || 'HW',
          default_tax_rate: Number(s.default_tax_rate) || 20,
          default_currency: (s.default_currency as string) || 'USD',
          quote_validity_days: Number(s.quote_validity_days) || 30,
        }),
      );
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
        <Button loading={saveMutation.isPending} onClick={() => saveMutation.mutate(form)}>
          Kaydet
        </Button>
      </PageHeader>

      <div className="space-y-6">
        {/* Display Settings */}
        <DisplaySettingsSection />

        {/* Email Settings */}
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

        {/* Meeting Link — visible to all roles */}
        <MeetingLinkSection />

        {/* Stage Configuration — sales_manager only */}
        {user?.role === 'sales_manager' && <StageConfigSection />}

        {/* Sharing Rules & Webhooks — sales_manager only */}
        {user?.role === 'sales_manager' && <SharingRulesSection />}
        {user?.role === 'sales_manager' && <WebhookSettings />}
        {user?.role === 'sales_manager' && <NotificationChannelsSection />}
      </div>
    </div>
  );
}

/* ── Display Settings Section ── */
function DisplaySettingsSection() {
  const t = useT();
  const { theme, setTheme, language, setLanguage, fontSizeOffset, setFontSizeOffset } =
    usePreferencesStore();

  return (
    <Card title={t('settings.display')}>
      <div className="space-y-6">
        {/* Theme */}
        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700">
            {t('settings.theme')}
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setTheme('light')}
              className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors ${
                theme === 'light'
                  ? 'border-honeywell-red bg-honeywell-light/30 text-honeywell-red'
                  : 'border-gray-200 text-gray-600 hover:border-gray-300'
              }`}
            >
              <Sun size={16} />
              {t('settings.theme_light')}
            </button>
            <button
              type="button"
              onClick={() => setTheme('dark')}
              className={`flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm font-medium transition-colors ${
                theme === 'dark'
                  ? 'border-honeywell-red bg-honeywell-light/30 text-honeywell-red'
                  : 'border-gray-200 text-gray-600 hover:border-gray-300'
              }`}
            >
              <Moon size={16} />
              {t('settings.theme_dark')}
            </button>
          </div>
        </div>

        {/* Language */}
        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700">
            {t('settings.language')}
          </label>
          <div className="flex flex-wrap gap-2">
            {LANGUAGE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setLanguage(opt.value as 'tr' | 'en' | 'de' | 'fr' | 'es')}
                className={`rounded-lg border px-4 py-2 text-sm font-medium transition-colors ${
                  language === opt.value
                    ? 'border-honeywell-red bg-honeywell-light/30 text-honeywell-red'
                    : 'border-gray-200 text-gray-600 hover:border-gray-300'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Font Size */}
        <div>
          <label className="mb-2 block text-sm font-medium text-gray-700">
            {t('settings.font_size')} ({fontSizeOffset >= 0 ? '+' : ''}
            {fontSizeOffset}px)
          </label>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setFontSizeOffset(fontSizeOffset - 1)}
              disabled={fontSizeOffset <= -4}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 text-gray-600 transition-colors hover:border-gray-300 disabled:opacity-40 disabled:cursor-not-allowed"
              title={t('settings.font_decrease')}
            >
              <Minus size={16} />
            </button>
            <div className="flex h-2 w-40 items-center rounded-full bg-gray-200">
              <div
                className="h-2 rounded-full bg-honeywell-red transition-all"
                style={{ width: `${((fontSizeOffset + 4) / 8) * 100}%` }}
              />
            </div>
            <button
              type="button"
              onClick={() => setFontSizeOffset(fontSizeOffset + 1)}
              disabled={fontSizeOffset >= 4}
              className="flex h-9 w-9 items-center justify-center rounded-lg border border-gray-200 text-gray-600 transition-colors hover:border-gray-300 disabled:opacity-40 disabled:cursor-not-allowed"
              title={t('settings.font_increase')}
            >
              <Plus size={16} />
            </button>
            {fontSizeOffset !== 0 && (
              <button
                type="button"
                onClick={() => setFontSizeOffset(0)}
                className="flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-xs text-gray-500 transition-colors hover:border-gray-300"
                title={t('settings.font_reset')}
              >
                <RotateCcw size={12} />
                {t('settings.font_reset')}
              </button>
            )}
          </div>
        </div>
      </div>
    </Card>
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
      queueMicrotask(() =>
        setEmailForm({
          email_address: creds.email_address || '',
          email_password: '',
          imap_host: creds.imap_host || '',
          imap_port: creds.imap_port || 993,
          smtp_host: creds.smtp_host || '',
          smtp_port: creds.smtp_port || 587,
        }),
      );
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
  const canSave =
    emailForm.email_address.length > 3 && (emailForm.email_password.length > 0 || isConfigured);

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
              placeholder={
                isConfigured ? '(degistirmek icin yeni sifre girin)' : 'Sifre veya App Password'
              }
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
                  onChange={(e) =>
                    setEmailForm((p) => ({ ...p, imap_port: Number(e.target.value) }))
                  }
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
                  onChange={(e) =>
                    setEmailForm((p) => ({ ...p, smtp_port: Number(e.target.value) }))
                  }
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

/* ── Stage Configuration Section ── */
function StageConfigSection() {
  const queryClient = useQueryClient();
  const [stages, setStages] = useState<StageConfig[]>([]);

  const { data, isLoading } = useQuery({
    queryKey: ['stage-config'],
    queryFn: settingsApi.getStageConfig,
  });

  useEffect(() => {
    if (data?.items) {
      queueMicrotask(() => setStages(data.items));
    }
  }, [data]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const payload = stages.map((s) => ({
        stage_name: s.stage_name,
        label: s.label,
        probability_pct: s.probability_pct,
        rotting_threshold_days: s.rotting_threshold_days,
      }));
      return settingsApi.updateStageConfig(payload);
    },
    onSuccess: () => {
      toast.success('Asama ayarlari kaydedildi');
      queryClient.invalidateQueries({ queryKey: ['stage-config'] });
    },
    onError: () => toast.error('Asama ayarlari kaydedilemedi'),
  });

  const updateStage = (index: number, field: keyof StageConfig, value: string | number) => {
    setStages((prev) => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: value };
      return updated;
    });
  };

  if (isLoading) return <Skeleton variant="card" />;

  return (
    <Card title="Asama Ayarlari">
      <p className="mb-4 text-xs text-gray-500">
        Firsat asamalarinin olasilik yuzdelerini ve rotting esiklerini yapilandirin.
      </p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left">
              <th className="pb-2 pr-4 font-medium text-gray-600">Asama</th>
              <th className="pb-2 pr-4 font-medium text-gray-600">Etiket</th>
              <th className="pb-2 pr-4 font-medium text-gray-600">Olasilik %</th>
              <th className="pb-2 font-medium text-gray-600">Rotting Esigi (gun)</th>
            </tr>
          </thead>
          <tbody>
            {stages.map((stage, idx) => (
              <tr key={stage.stage_name} className="border-b border-gray-100 last:border-0">
                <td className="py-2 pr-4">
                  <span className="font-mono text-xs text-gray-500">{stage.stage_name}</span>
                </td>
                <td className="py-2 pr-4">
                  <input
                    type="text"
                    value={stage.label}
                    onChange={(e) => updateStage(idx, 'label', e.target.value)}
                    className="w-full rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:border-honeywell-red focus:outline-none"
                  />
                </td>
                <td className="py-2 pr-4">
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={stage.probability_pct}
                    onChange={(e) => updateStage(idx, 'probability_pct', Number(e.target.value))}
                    className="w-24 rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:border-honeywell-red focus:outline-none"
                  />
                </td>
                <td className="py-2">
                  <input
                    type="number"
                    min={0}
                    value={stage.rotting_threshold_days}
                    onChange={(e) =>
                      updateStage(idx, 'rotting_threshold_days', Number(e.target.value))
                    }
                    className="w-24 rounded-md border border-gray-200 px-2 py-1.5 text-sm focus:border-honeywell-red focus:outline-none"
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex justify-end">
        <Button onClick={() => saveMutation.mutate()} loading={saveMutation.isPending}>
          <Save size={14} className="mr-1" />
          Asama Ayarlarini Kaydet
        </Button>
      </div>
    </Card>
  );
}

/* ── Notification Channels Section ── */
function NotificationChannelsSection() {
  const [slackUrl, setSlackUrl] = useState('');
  const [teamsUrl, setTeamsUrl] = useState('');

  const { data: channelsData, isLoading } = useQuery({
    queryKey: ['notification-channels'],
    queryFn: settingsApi.getNotificationChannels,
  });

  const testMutation = useMutation({
    mutationFn: (payload: { slack_url?: string; teams_url?: string }) =>
      settingsApi.testNotificationChannel(payload),
    onSuccess: (result) => {
      const results = result.data;
      if (results.slack === true) {
        toast.success('Slack test bildirimi gonderildi');
      } else if (results.slack === false) {
        toast.error('Slack test bildirimi gonderilemedi');
      }
      if (results.teams === true) {
        toast.success('Teams test bildirimi gonderildi');
      } else if (results.teams === false) {
        toast.error('Teams test bildirimi gonderilemedi');
      }
    },
    onError: () => toast.error('Test bildirimi gonderilemedi'),
  });

  if (isLoading) return <Skeleton variant="card" />;

  const isSlackConfigured = channelsData?.data?.slack_configured ?? false;
  const isTeamsConfigured = channelsData?.data?.teams_configured ?? false;

  return (
    <Card title="Bildirim Kanallari">
      <div className="space-y-6">
        <p className="text-xs text-gray-500">
          Firsat ve teklif bildirimleri icin Slack ve Microsoft Teams entegrasyonu. Webhook
          URL&apos;leri .env dosyasinda yapilandirilir.
        </p>

        {/* Slack */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bell size={16} className="text-gray-500" />
              <span className="text-sm font-medium text-gray-700">Slack</span>
            </div>
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                isSlackConfigured ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isSlackConfigured ? 'bg-green-500' : 'bg-gray-400'
                }`}
              />
              {isSlackConfigured ? 'Bagli' : 'Bagli Degil'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Input
              label="Slack Webhook URL"
              value={slackUrl}
              onChange={(e) => setSlackUrl(e.target.value)}
              placeholder="https://hooks.slack.com/services/..."
            />
            <Button
              variant="secondary"
              loading={testMutation.isPending}
              disabled={!slackUrl}
              onClick={() => testMutation.mutate({ slack_url: slackUrl })}
              className="mt-5 shrink-0"
            >
              Test Et
            </Button>
          </div>
        </div>

        {/* Teams */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bell size={16} className="text-gray-500" />
              <span className="text-sm font-medium text-gray-700">Microsoft Teams</span>
            </div>
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                isTeamsConfigured ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isTeamsConfigured ? 'bg-green-500' : 'bg-gray-400'
                }`}
              />
              {isTeamsConfigured ? 'Bagli' : 'Bagli Degil'}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Input
              label="Teams Webhook URL"
              value={teamsUrl}
              onChange={(e) => setTeamsUrl(e.target.value)}
              placeholder="https://outlook.office.com/webhook/..."
            />
            <Button
              variant="secondary"
              loading={testMutation.isPending}
              disabled={!teamsUrl}
              onClick={() => testMutation.mutate({ teams_url: teamsUrl })}
              className="mt-5 shrink-0"
            >
              Test Et
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ── Meeting Link Section ── */
const DURATION_OPTIONS = [
  { value: '15', label: '15 dakika' },
  { value: '30', label: '30 dakika' },
  { value: '45', label: '45 dakika' },
  { value: '60', label: '60 dakika' },
];

function MeetingLinkSection() {
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const [duration, setDuration] = useState('30');

  const { data: linksData, isLoading: linksLoading } = useQuery({
    queryKey: ['meeting-links'],
    queryFn: meetingsApi.listLinks,
  });

  const { data: bookingsData } = useQuery({
    queryKey: ['meeting-bookings'],
    queryFn: meetingsApi.listBookings,
  });

  const createMutation = useMutation({
    mutationFn: () => meetingsApi.createLink({ title, duration_minutes: Number(duration) }),
    onSuccess: () => {
      toast.success('Toplanti linki olusturuldu');
      setTitle('');
      queryClient.invalidateQueries({ queryKey: ['meeting-links'] });
    },
    onError: () => toast.error('Toplanti linki olusturulamadi'),
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: number) => meetingsApi.deactivateLink(id),
    onSuccess: () => {
      toast.success('Toplanti linki devre disi birakildi');
      queryClient.invalidateQueries({ queryKey: ['meeting-links'] });
    },
    onError: () => toast.error('Islem basarisiz'),
  });

  const links: MeetingLink[] = linksData?.data || [];
  const bookings: MeetingBooking[] = bookingsData?.data || [];

  const copyUrl = (slug: string) => {
    const url = `${window.location.origin}/api/v1/meetings/book/${slug}`;
    navigator.clipboard.writeText(url);
    toast.success('Link kopyalandi');
  };

  if (linksLoading) return <Skeleton variant="card" />;

  return (
    <Card title="Toplanti Linkim">
      <div className="space-y-6">
        {/* Create form */}
        <div className="space-y-3">
          <p className="text-xs text-gray-500">
            Musterilerinizin sizinle toplanti planlamasini kolaylastirin.
          </p>
          <div className="flex items-end gap-3">
            <Input
              label="Toplanti Basligi"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Tanitim Gorusmesi"
              className="flex-1"
            />
            <Select
              label="Sure"
              options={DURATION_OPTIONS}
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
            />
            <Button
              onClick={() => createMutation.mutate()}
              loading={createMutation.isPending}
              disabled={!title.trim()}
              className="shrink-0"
            >
              Olustur
            </Button>
          </div>
        </div>

        {/* Active links */}
        {links.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-gray-700">Aktif Linkler</h4>
            <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
              {links.map((lnk) => (
                <div key={lnk.id} className="flex items-center justify-between px-4 py-3">
                  <div>
                    <span className="text-sm font-medium text-gray-800">{lnk.title}</span>
                    <span className="ml-2 text-xs text-gray-400">{lnk.duration_minutes} dk</span>
                    <div className="mt-0.5 flex items-center gap-1.5">
                      <Link2 size={12} className="text-gray-400" />
                      <span className="text-xs font-mono text-gray-500">
                        /meetings/book/{lnk.slug}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => copyUrl(lnk.slug)}
                      className="flex items-center gap-1 rounded-md border border-gray-200 px-2.5 py-1.5 text-xs text-gray-600 hover:bg-gray-50 transition-colors"
                    >
                      <Copy size={12} />
                      Kopyala
                    </button>
                    {lnk.is_active && (
                      <button
                        type="button"
                        onClick={() => deactivateMutation.mutate(lnk.id)}
                        className="flex items-center gap-1 rounded-md border border-red-200 px-2.5 py-1.5 text-xs text-red-600 hover:bg-red-50 transition-colors"
                      >
                        <Trash2 size={12} />
                        Kapat
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Active bookings */}
        {bookings.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-gray-700">Aktif Rezervasyonlar</h4>
            <div className="divide-y divide-gray-100 rounded-lg border border-gray-200">
              {bookings.map((b) => (
                <div key={b.id} className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-3">
                    <Calendar size={16} className="text-gray-400 shrink-0" />
                    <div>
                      <span className="text-sm font-medium text-gray-800">{b.booker_name}</span>
                      <span className="ml-2 text-xs text-gray-400">{b.booker_email}</span>
                      <div className="mt-0.5 text-xs text-gray-500">
                        {new Date(b.scheduled_at).toLocaleString('tr-TR')}
                      </div>
                      {b.notes && <p className="mt-0.5 text-xs text-gray-400 italic">{b.notes}</p>}
                    </div>
                  </div>
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      b.status === 'confirmed'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-gray-100 text-gray-500'
                    }`}
                  >
                    {b.status === 'confirmed' ? 'Onaylandi' : b.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
