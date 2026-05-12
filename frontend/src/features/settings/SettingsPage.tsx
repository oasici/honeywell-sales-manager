import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  CheckCircle,
  AlertCircle,
  Trash2,
  Sun,
  Moon,
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
import { settingsApi, meetingsApi, opsApi } from '../../lib/api';
import { usePreferencesStore } from '../../stores/preferencesStore';
import { useAuthStore } from '../../stores/authStore';
import { useT } from '../../hooks/useT';
import { LANGUAGE_OPTIONS, type TranslationKey } from '../../lib/i18n';
import SharingRulesSection from './SharingRulesSection';
import WebhookSettings from './WebhookSettings';
import { currentLocale } from '../../lib/formatters';

import type { StageConfig, MeetingLink, MeetingBooking } from '../../lib/types';

interface SettingsData {
  quote_prefix: string;
  default_tax_rate: number;
  default_currency: string;
  quote_validity_days: number;
}

function currencyOptions(t: (key: TranslationKey) => string) {
  return [
    { value: 'TRY', label: `TRY - ${t('currency.try')}` },
    { value: 'USD', label: `USD - ${t('currency.usd')}` },
    { value: 'EUR', label: `EUR - ${t('currency.eur')}` },
  ];
}

const DEFAULTS: SettingsData = {
  quote_prefix: 'HW',
  default_tax_rate: 20,
  default_currency: 'USD',
  quote_validity_days: 30,
};

export default function SettingsPage() {
  const t = useT();
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
      // Round-12 R12-FE-4 — drop the `as unknown as` escape hatch.
      // SettingsData is a primitive-only struct and the spread
      // satisfies Record<string, unknown> structurally; no type
      // double-cast required.
      settingsApi.updateSettings({ ...payload }),
    onSuccess: () => {
      toast.success(t('settings.toast_saved'));
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
    onError: () => toast.error(t('settings.toast_save_failed')),
  });

  const updateField = (field: keyof SettingsData, value: string | number) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  if (isLoading) {
    return (
      <div>
        <PageHeader title={t('settings.title')} description={t('settings.description')} />
        <div className="space-y-4">
          <Skeleton variant="card" count={2} />
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader title={t('settings.title')} description={t('settings.description')}>
        <Button loading={saveMutation.isPending} onClick={() => saveMutation.mutate(form)}>
          <Save size={14} />
          {t('settings.save')}
        </Button>
      </PageHeader>

      <div className="space-y-6">
        {/* Display Settings */}
        <DisplaySettingsSection />

        {/* Email Settings */}
        <EmailSettingsSection />

        {/* Quote Settings */}
        <Card title={t('settings.quote_settings')}>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label={t('settings.quote_prefix')}
              value={form.quote_prefix}
              onChange={(e) => updateField('quote_prefix', e.target.value)}
              placeholder="HW"
              helperText={t('settings.quote_prefix_help')}
            />
            <Input
              label={t('settings.default_tax_rate')}
              type="number"
              min={0}
              max={100}
              value={form.default_tax_rate}
              onChange={(e) => updateField('default_tax_rate', Number(e.target.value))}
            />
            <Select
              label={t('settings.default_currency')}
              options={currencyOptions(t)}
              value={form.default_currency}
              onChange={(e) => updateField('default_currency', e.target.value)}
            />
            <Input
              label={t('settings.quote_validity_days')}
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
        {user?.role === 'sales_manager' && <FeatureModulesSection />}
      </div>
    </div>
  );
}

function FeatureModulesSection() {
  const t = useT();
  const { data, isLoading } = useQuery({
    queryKey: ['ops-feature-flags'],
    queryFn: opsApi.getFeatureFlags,
  });
  const entries = data
    ? Object.entries(data)
        .filter(([k]) => k.startsWith('FEATURE_'))
        .sort(([a], [b]) => a.localeCompare(b))
    : [];

  return (
    <Card title={t('settings.modules_title')}>
      <p className="mb-4 text-sm text-slate-600 dark:text-slate-400">
        {t('settings.modules_subtitle')}
      </p>
      {isLoading ? (
        <Skeleton variant="line" count={6} />
      ) : (
        <div className="max-h-96 overflow-y-auto rounded-2xl border border-slate-200 dark:border-slate-800">
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {entries.map(([name, on]) => (
              <li
                key={name}
                className="flex items-center justify-between px-4 py-2.5"
              >
                <span className="font-mono text-[12px] text-slate-700 dark:text-slate-200">
                  {name}
                </span>
                <span
                  className={[
                    'inline-flex h-5 items-center gap-1.5 rounded-full px-2 text-[10px] font-bold ring-1 ring-inset',
                    on
                      ? 'bg-emerald-50 text-emerald-700 ring-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-400 dark:ring-emerald-900/40'
                      : 'bg-slate-50 text-slate-500 ring-slate-100 dark:bg-slate-800 dark:text-slate-400 dark:ring-slate-700',
                  ].join(' ')}
                >
                  <span
                    className={[
                      'inline-block h-1.5 w-1.5 rounded-full',
                      on ? 'bg-emerald-500' : 'bg-slate-400',
                    ].join(' ')}
                  />
                  {on ? 'ON' : 'OFF'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

/* ── Display Settings Section ── */
function DisplaySettingsSection() {
  const t = useT();
  const { theme, setTheme, language, setLanguage } = usePreferencesStore();

  // Shared segmented-button style — sits in a slate-50 well with a white
  // active pill (matches QuoteListPage / ContractListPage tabs).
  const segItem = (active: boolean) =>
    [
      'inline-flex h-9 items-center gap-2 rounded-[10px] px-3 text-[13px] font-medium transition-all',
      'focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20',
      active
        ? 'bg-white text-slate-900 shadow-(--shadow-xs) dark:bg-slate-800 dark:text-white'
        : 'text-slate-600 hover:bg-white/60 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800/60 dark:hover:text-slate-200',
    ].join(' ');

  return (
    <Card title={t('settings.display')}>
      <div className="space-y-6">
        {/* Theme */}
        <div>
          <label className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300">
            {t('settings.theme')}
          </label>
          <div className="inline-flex gap-1 rounded-[12px] border border-slate-200 bg-slate-50/80 p-1 dark:border-slate-800 dark:bg-slate-900/40">
            <button type="button" onClick={() => setTheme('light')} className={segItem(theme === 'light')}>
              <Sun size={14} />
              {t('settings.theme_light')}
            </button>
            <button type="button" onClick={() => setTheme('dark')} className={segItem(theme === 'dark')}>
              <Moon size={14} />
              {t('settings.theme_dark')}
            </button>
          </div>
        </div>

        {/* Language */}
        <div>
          <label className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300">
            {t('settings.language')}
          </label>
          <div className="inline-flex flex-wrap gap-1 rounded-[12px] border border-slate-200 bg-slate-50/80 p-1 dark:border-slate-800 dark:bg-slate-900/40">
            {LANGUAGE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setLanguage(opt.value as 'tr' | 'en' | 'de' | 'fr' | 'es')}
                className={segItem(language === opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

      </div>
    </Card>
  );
}

/* ── Email Settings Section ── */
function EmailSettingsSection() {
  const t = useT();
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
      toast.success(t('settings.email_toast_saved'));
      queryClient.invalidateQueries({ queryKey: ['email-credentials'] });
    },
    onError: () => toast.error(t('settings.email_toast_save_failed')),
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
      setTestResult({ success: false, message: t('settings.email_test_failed') });
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
      toast.success(t('settings.email_toast_deleted'));
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
    onError: () => toast.error(t('settings.email_toast_delete_failed')),
  });

  if (isLoading) return <Skeleton variant="card" />;

  const isConfigured = creds?.is_configured;
  const canSave =
    emailForm.email_address.length > 3 && (emailForm.email_password.length > 0 || isConfigured);

  return (
    <>
      <Card title={t('settings.email_card_title')}>
        <div className="space-y-4">
          {/* Connection status */}
          {isConfigured && (
            <div className="flex items-center justify-between rounded-lg bg-green-50 border border-green-200 p-3">
              <div className="flex items-center gap-2 text-sm text-green-700">
                <CheckCircle size={16} className="shrink-0" />
                <span>
                  {t('settings.email_connected_prefix')}: <strong>{creds.email_address}</strong> (
                  {creds.imap_host})
                </span>
              </div>
              <button
                type="button"
                onClick={() => setShowDeleteConfirm(true)}
                className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-red-600 hover:bg-red-50 transition-colors"
              >
                <Trash2 size={14} />
                {t('settings.email_delete_connection')}
              </button>
            </div>
          )}

          {/* Email + Password */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label={t('settings.email_address')}
              type="email"
              value={emailForm.email_address}
              onChange={(e) => handleEmailChange(e.target.value)}
              placeholder={t('settings.email_address_placeholder')}
            />
            <Input
              label={t('settings.email_password')}
              type="password"
              value={emailForm.email_password}
              onChange={(e) => {
                setEmailForm((p) => ({ ...p, email_password: e.target.value }));
                setTestResult(null);
              }}
              placeholder={
                isConfigured
                  ? t('settings.email_password_placeholder_change')
                  : t('settings.email_password_placeholder_new')
              }
            />
          </div>

          {/* IMAP/SMTP info */}
          {emailForm.imap_host && !editingServer && (
            <div>
              <div className="grid grid-cols-2 gap-4 rounded-lg border border-slate-200 bg-slate-50 p-4 sm:grid-cols-4">
                <div>
                  <span className="text-xs font-medium text-slate-500">IMAP</span>
                  <p className="text-sm text-slate-800 font-mono">{emailForm.imap_host}</p>
                </div>
                <div>
                  <span className="text-xs font-medium text-slate-500">
                    {t('settings.email_imap_port')}
                  </span>
                  <p className="text-sm text-slate-800 font-mono">{emailForm.imap_port}</p>
                </div>
                <div>
                  <span className="text-xs font-medium text-slate-500">SMTP</span>
                  <p className="text-sm text-slate-800 font-mono">{emailForm.smtp_host}</p>
                </div>
                <div>
                  <span className="text-xs font-medium text-slate-500">
                    {t('settings.email_smtp_port')}
                  </span>
                  <p className="text-sm text-slate-800 font-mono">{emailForm.smtp_port}</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setEditingServer(true)}
                className="mt-2 text-xs text-slate-500 hover:text-honeywell-red transition-colors"
              >
                {t('settings.email_server_edit')}
              </button>
            </div>
          )}

          {/* Editable IMAP/SMTP fields */}
          {editingServer && (
            <div>
              <div className="grid grid-cols-1 gap-4 rounded-lg border border-honeywell-light bg-red-50/30 p-4 sm:grid-cols-2">
                <Input
                  label={t('settings.email_imap_server')}
                  value={emailForm.imap_host}
                  onChange={(e) => setEmailForm((p) => ({ ...p, imap_host: e.target.value }))}
                />
                <Input
                  label={t('settings.email_imap_port')}
                  type="number"
                  value={String(emailForm.imap_port)}
                  onChange={(e) =>
                    setEmailForm((p) => ({ ...p, imap_port: Number(e.target.value) }))
                  }
                />
                <Input
                  label={t('settings.email_smtp_server')}
                  value={emailForm.smtp_host}
                  onChange={(e) => setEmailForm((p) => ({ ...p, smtp_host: e.target.value }))}
                />
                <Input
                  label={t('settings.email_smtp_port')}
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
                className="mt-2 text-xs text-slate-500 hover:text-honeywell-red transition-colors"
              >
                {t('settings.email_server_edit_close')}
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
              {t('settings.email_test_connection')}
            </Button>
            <Button
              onClick={() => saveMutation.mutate()}
              loading={saveMutation.isPending}
              disabled={!canSave}
            >
              {t('settings.email_save')}
            </Button>
          </div>
        </div>
      </Card>

      {/* Delete confirmation */}
      <ConfirmDialog
        isOpen={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(false)}
        onConfirm={() => deleteMutation.mutate()}
        title={t('settings.email_delete_title')}
        message={t('settings.email_delete_message')}
        confirmLabel={t('common.delete')}
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </>
  );
}

/* ── Stage Configuration Section ── */
function StageConfigSection() {
  const t = useT();
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
      toast.success(t('settings.stage_toast_saved'));
      queryClient.invalidateQueries({ queryKey: ['stage-config'] });
    },
    onError: () => toast.error(t('settings.stage_toast_failed')),
  });

  const updateStage = (index: number, field: keyof StageConfig, value: string | number) => {
    setStages((prev) => {
      const updated = [...prev];
      // Round-10 R10-FE-13 — bail when the index is out-of-range
      // rather than constructing a partial StageConfig.
      const current = updated[index];
      if (!current) return prev;
      updated[index] = { ...current, [field]: value };
      return updated;
    });
  };

  if (isLoading) return <Skeleton variant="card" />;

  return (
    <Card title={t('settings.stage_card_title')}>
      <p className="mb-4 text-xs text-slate-500">{t('settings.stage_card_description')}</p>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left">
              <th className="pb-2 pr-4 font-medium text-slate-600">
                {t('settings.stage_col_stage')}
              </th>
              <th className="pb-2 pr-4 font-medium text-slate-600">
                {t('settings.stage_col_label')}
              </th>
              <th className="pb-2 pr-4 font-medium text-slate-600">
                {t('settings.stage_col_probability')}
              </th>
              <th className="pb-2 font-medium text-slate-600">{t('settings.stage_col_rotting')}</th>
            </tr>
          </thead>
          <tbody>
            {stages.map((stage, idx) => (
              <tr key={stage.stage_name} className="border-b border-slate-100 last:border-0">
                <td className="py-2 pr-4">
                  <span className="font-mono text-xs text-slate-500">{stage.stage_name}</span>
                </td>
                <td className="py-2 pr-4">
                  <input
                    type="text"
                    value={stage.label}
                    onChange={(e) => updateStage(idx, 'label', e.target.value)}
                    className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-sm focus:border-honeywell-red focus:outline-none"
                  />
                </td>
                <td className="py-2 pr-4">
                  <input
                    type="number"
                    min={0}
                    max={100}
                    value={stage.probability_pct}
                    onChange={(e) => updateStage(idx, 'probability_pct', Number(e.target.value))}
                    className="w-24 rounded-md border border-slate-200 px-2 py-1.5 text-sm focus:border-honeywell-red focus:outline-none"
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
                    className="w-24 rounded-md border border-slate-200 px-2 py-1.5 text-sm focus:border-honeywell-red focus:outline-none"
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
          {t('settings.stage_save')}
        </Button>
      </div>
    </Card>
  );
}

/* ── Notification Channels Section ── */
function NotificationChannelsSection() {
  const t = useT();
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
        toast.success(t('settings.slack_test_ok'));
      } else if (results.slack === false) {
        toast.error(t('settings.slack_test_fail'));
      }
      if (results.teams === true) {
        toast.success(t('settings.teams_test_ok'));
      } else if (results.teams === false) {
        toast.error(t('settings.teams_test_fail'));
      }
    },
    onError: () => toast.error(t('settings.notif_test_fail')),
  });

  if (isLoading) return <Skeleton variant="card" />;

  const isSlackConfigured = channelsData?.data?.slack_configured ?? false;
  const isTeamsConfigured = channelsData?.data?.teams_configured ?? false;

  return (
    <Card title={t('settings.notif_channels_title')}>
      <div className="space-y-6">
        <p className="text-xs text-slate-500">{t('settings.notif_channels_desc')}</p>

        {/* Slack */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bell size={16} className="text-slate-500" />
              <span className="text-sm font-medium text-slate-700">{t('settings.slack_label')}</span>
            </div>
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                isSlackConfigured ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isSlackConfigured ? 'bg-green-500' : 'bg-gray-400'
                }`}
              />
              {isSlackConfigured ? t('settings.connected') : t('settings.not_connected')}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Input
              label={t('settings.slack_webhook')}
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
              {t('settings.test')}
            </Button>
          </div>
        </div>

        {/* Teams */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Bell size={16} className="text-slate-500" />
              <span className="text-sm font-medium text-slate-700">{t('settings.teams_label')}</span>
            </div>
            <span
              className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                isTeamsConfigured ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'
              }`}
            >
              <span
                className={`h-1.5 w-1.5 rounded-full ${
                  isTeamsConfigured ? 'bg-green-500' : 'bg-gray-400'
                }`}
              />
              {isTeamsConfigured ? t('settings.connected') : t('settings.not_connected')}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Input
              label={t('settings.teams_webhook')}
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
              {t('settings.test')}
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

/* ── Meeting Link Section ── */
function MeetingLinkSection() {
  const t = useT();
  const durationOptions = [
    { value: '15', label: t('settings.duration_min_15') },
    { value: '30', label: t('settings.duration_min_30') },
    { value: '45', label: t('settings.duration_min_45') },
    { value: '60', label: t('settings.duration_min_60') },
  ];
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
      toast.success(t('settings.meeting_toast_created'));
      setTitle('');
      queryClient.invalidateQueries({ queryKey: ['meeting-links'] });
    },
    onError: () => toast.error(t('settings.meeting_toast_create_failed')),
  });

  const deactivateMutation = useMutation({
    mutationFn: (id: number) => meetingsApi.deactivateLink(id),
    onSuccess: () => {
      toast.success(t('settings.meeting_toast_deactivated'));
      queryClient.invalidateQueries({ queryKey: ['meeting-links'] });
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  const links: MeetingLink[] = linksData?.data || [];
  const bookings: MeetingBooking[] = bookingsData?.data || [];

  const copyUrl = (slug: string) => {
    const url = `${window.location.origin}/api/v1/meetings/book/${slug}`;
    navigator.clipboard.writeText(url);
    toast.success(t('settings.link_copied'));
  };

  if (linksLoading) return <Skeleton variant="card" />;

  return (
    <Card title={t('settings.meeting_card_title')}>
      <div className="space-y-6">
        {/* Create form */}
        <div className="space-y-3">
          <p className="text-xs text-slate-500">{t('settings.meeting_card_desc')}</p>
          <div className="flex items-end gap-3">
            <Input
              label={t('settings.meeting_title_field')}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={t('settings.meeting_title_ph')}
              className="flex-1"
            />
            <Select
              label={t('settings.duration')}
              options={durationOptions}
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
            />
            <Button
              onClick={() => createMutation.mutate()}
              loading={createMutation.isPending}
              disabled={!title.trim()}
              className="shrink-0"
            >
              {t('settings.create')}
            </Button>
          </div>
        </div>

        {/* Active links */}
        {links.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-sm font-medium text-slate-700">{t('settings.active_links')}</h4>
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
              {links.map((lnk) => (
                <div key={lnk.id} className="flex items-center justify-between px-4 py-3">
                  <div>
                    <span className="text-sm font-medium text-slate-800">{lnk.title}</span>
                    <span className="ml-2 text-xs text-slate-400">
                      {lnk.duration_minutes} {t('common.minutes_short')}
                    </span>
                    <div className="mt-0.5 flex items-center gap-1.5">
                      <Link2 size={12} className="text-slate-400" />
                      <span className="text-xs font-mono text-slate-500">
                        /meetings/book/{lnk.slug}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => copyUrl(lnk.slug)}
                      className="flex items-center gap-1 rounded-md border border-slate-200 px-2.5 py-1.5 text-xs text-slate-600 hover:bg-slate-50 transition-colors"
                    >
                      <Copy size={12} />
                      {t('settings.copy')}
                    </button>
                    {lnk.is_active && (
                      <button
                        type="button"
                        onClick={() => deactivateMutation.mutate(lnk.id)}
                        className="flex items-center gap-1 rounded-md border border-red-200 px-2.5 py-1.5 text-xs text-red-600 hover:bg-red-50 transition-colors"
                      >
                        <Trash2 size={12} />
                        {t('settings.close_link')}
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
            <h4 className="text-sm font-medium text-slate-700">{t('settings.active_bookings')}</h4>
            <div className="divide-y divide-slate-100 rounded-lg border border-slate-200">
              {bookings.map((b) => (
                <div key={b.id} className="flex items-center justify-between px-4 py-3">
                  <div className="flex items-center gap-3">
                    <Calendar size={16} className="text-slate-400 shrink-0" />
                    <div>
                      <span className="text-sm font-medium text-slate-800">{b.booker_name}</span>
                      <span className="ml-2 text-xs text-slate-400">{b.booker_email}</span>
                      <div className="mt-0.5 text-xs text-slate-500">
                        {new Date(b.scheduled_at).toLocaleString(currentLocale())}
                      </div>
                      {b.notes && <p className="mt-0.5 text-xs text-slate-400 italic">{b.notes}</p>}
                    </div>
                  </div>
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      b.status === 'confirmed'
                        ? 'bg-green-100 text-green-700'
                        : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {b.status === 'confirmed' ? t('settings.booking_status_confirmed') : b.status}
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
