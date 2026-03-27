import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Mail, CheckCircle, AlertCircle, Shield } from 'lucide-react';
import { Modal } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Button } from '../../components/ui/Button';
import { settingsApi } from '../../lib/api';
import { useAuthStore } from '../../stores/authStore';

interface EmailSetupModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function EmailSetupModal({ isOpen, onClose }: EmailSetupModalProps) {
  const user = useAuthStore((s) => s.user);
  const setAuth = useAuthStore((s) => s.setAuth);
  const token = useAuthStore((s) => s.token);
  const refreshToken = useAuthStore((s) => s.refreshToken);

  const [form, setForm] = useState({
    email_address: '',
    email_password: '',
    imap_host: 'outlook.office365.com',
    imap_port: 993,
    smtp_host: 'smtp.office365.com',
    smtp_port: 587,
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);

  const saveMutation = useMutation({
    mutationFn: () => settingsApi.saveEmailCredentials(form),
    onSuccess: () => {
      toast.success('Email bilgileri kaydedildi');
      // Update user in store to mark email_setup_completed
      if (user && token && refreshToken) {
        setAuth(token, refreshToken, { ...user, email_setup_completed: true });
      }
      onClose();
    },
    onError: () => toast.error('Email bilgileri kaydedilemedi'),
  });

  const testMutation = useMutation({
    mutationFn: async () => {
      // Test directly without saving
      return settingsApi.testEmailConnection({
        email_address: form.email_address,
        email_password: form.email_password,
        imap_host: form.imap_host || undefined,
        imap_port: form.imap_port || undefined,
      });
    },
    onSuccess: (result) => {
      setTestResult(result);
      if (result.success) {
        toast.success(result.message);
      } else {
        toast.error(result.message);
      }
    },
    onError: () => {
      setTestResult({ success: false, message: 'Baglanti testi basarisiz' });
      toast.error('Baglanti testi basarisiz');
    },
  });

  const updateField = (field: string, value: string | number) => {
    setForm((prev) => ({ ...prev, [field]: value }));
    setTestResult(null);
  };

  const canSave = form.email_address.length > 3 && form.email_password.length > 0;

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="" size="lg">
      <div className="space-y-6">
        {/* Header */}
        <div className="text-center">
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-honeywell-red/10">
            <Mail size={28} className="text-honeywell-red" />
          </div>
          <h2 className="text-xl font-bold text-gray-900">Email Baglantisi Kurulumu</h2>
          <p className="mt-1 text-sm text-gray-500">
            Gelen kutunuzu baglamak icin Outlook email bilgilerinizi giriniz.
            <br />
            Bu bilgiler guvenli bir sekilde saklanacaktir.
          </p>
        </div>

        {/* Security note */}
        <div className="flex items-start gap-3 rounded-lg bg-blue-50 border border-blue-200 p-3">
          <Shield size={16} className="mt-0.5 shrink-0 text-blue-600" />
          <p className="text-xs text-blue-700">
            Email bilgileriniz sifrelenerek sunucuda saklanir ve sadece email okuma/gonderme icin kullanilir.
            Ayarlar sayfasindan istediginiz zaman degistirebilirsiniz.
          </p>
        </div>

        {/* Form */}
        <div className="space-y-4">
          <Input
            label="Email Adresi"
            type="email"
            placeholder="ornek@sirket.com"
            value={form.email_address}
            onChange={(e) => updateField('email_address', e.target.value)}
            required
          />
          <Input
            label="Email Sifresi"
            type="password"
            placeholder="********"
            value={form.email_password}
            onChange={(e) => updateField('email_password', e.target.value)}
            required
          />

          {/* Advanced settings toggle */}
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="text-xs text-gray-500 hover:text-gray-700 transition-colors"
          >
            {showAdvanced ? '- Gelismis ayarlari gizle' : '+ Gelismis ayarlar (IMAP/SMTP)'}
          </button>

          {showAdvanced && (
            <div className="grid grid-cols-2 gap-4 rounded-lg border border-gray-200 bg-gray-50 p-4">
              <Input
                label="IMAP Sunucusu"
                value={form.imap_host}
                onChange={(e) => updateField('imap_host', e.target.value)}
              />
              <Input
                label="IMAP Port"
                type="number"
                value={String(form.imap_port)}
                onChange={(e) => updateField('imap_port', Number(e.target.value))}
              />
              <Input
                label="SMTP Sunucusu"
                value={form.smtp_host}
                onChange={(e) => updateField('smtp_host', e.target.value)}
              />
              <Input
                label="SMTP Port"
                type="number"
                value={String(form.smtp_port)}
                onChange={(e) => updateField('smtp_port', Number(e.target.value))}
              />
            </div>
          )}
        </div>

        {/* Test result */}
        {testResult && (
          <div
            className={`flex items-center gap-2 rounded-lg p-3 text-sm ${
              testResult.success
                ? 'bg-green-50 border border-green-200 text-green-700'
                : 'bg-red-50 border border-red-200 text-red-700'
            }`}
          >
            {testResult.success ? (
              <CheckCircle size={16} className="shrink-0" />
            ) : (
              <AlertCircle size={16} className="shrink-0" />
            )}
            {testResult.message}
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center justify-between pt-2">
          <Button
            variant="secondary"
            onClick={() => testMutation.mutate()}
            disabled={!canSave}
            loading={testMutation.isPending}
          >
            {testMutation.isPending ? 'Test ediliyor...' : 'Baglantiyi Test Et'}
          </Button>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={onClose}>
              Sonra Yap
            </Button>
            <Button
              onClick={() => saveMutation.mutate()}
              disabled={!canSave}
              loading={saveMutation.isPending}
            >
              Kaydet
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
