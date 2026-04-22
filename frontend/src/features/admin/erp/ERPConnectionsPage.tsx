import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Link } from 'react-router-dom';
import {
  CheckCircle2,
  CircleSlash,
  Plug,
  RefreshCw,
  Settings2,
  ShieldCheck,
  Trash2,
  TriangleAlert,
} from 'lucide-react';

import { PageHeader } from '../../../components/ui/PageHeader';
import { Card } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { Modal } from '../../../components/ui/Modal';
import {
  erpApi,
  type ERPConnection,
  type ERPConnectionCreate,
  type ERPConnectionType,
} from '../../../lib/api';

const CONNECTOR_OPTIONS: { value: ERPConnectionType; label: string; hint: string }[] = [
  {
    value: 'parasut',
    label: 'Paraşüt',
    hint: 'REST + OAuth2 — KOBİ, ön muhasebe, e-Fatura.',
  },
  {
    value: 'logo',
    label: 'Logo Tiger / Go',
    hint: 'XML-RPC — Logo Tiger 3, Go 3, Wolf ürün hatları.',
  },
  {
    value: 'netsis',
    label: 'Netsis',
    hint: 'XML-RPC — Netsis 3 Standard / Enterprise.',
  },
  {
    value: 'sap_b1',
    label: 'SAP Business One (v1.1)',
    hint: 'Service Layer REST — v3.1 sprintinde açılacak.',
  },
  {
    value: 'webhook',
    label: 'Jenerik Webhook',
    hint: 'Diğer ERP sistemlerinden push-only entegrasyon.',
  },
];

function formatRelative(value: string | null): string {
  if (!value) return 'Hiç';
  const ts = new Date(value).getTime();
  const delta = Date.now() - ts;
  if (!Number.isFinite(ts)) return 'Hiç';
  const mins = Math.round(delta / 60_000);
  if (mins < 1) return 'az önce';
  if (mins < 60) return `${mins} dk önce`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} sa önce`;
  const days = Math.round(hours / 24);
  return `${days} gün önce`;
}

export function ERPConnectionsPage() {
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);

  const connectionsQuery = useQuery({
    queryKey: ['erp', 'connections'],
    queryFn: () => erpApi.listConnections(),
    refetchInterval: 30_000,
  });

  const createMutation = useMutation({
    mutationFn: (body: ERPConnectionCreate) => erpApi.createConnection(body),
    onSuccess: () => {
      toast.success('ERP bağlantısı oluşturuldu');
      queryClient.invalidateQueries({ queryKey: ['erp', 'connections'] });
      setShowCreate(false);
    },
    onError: (err: unknown) => {
      const message = err instanceof Error ? err.message : 'Oluşturulamadı';
      toast.error(message);
    },
  });

  const testMutation = useMutation({
    mutationFn: (id: number) => erpApi.testConnection(id),
    onSuccess: (result) => {
      if (result.ok) {
        toast.success('Bağlantı doğrulandı');
      } else {
        toast.error(result.error || 'Bağlantı başarısız');
      }
    },
  });

  const syncMutation = useMutation({
    mutationFn: (id: number) =>
      erpApi.triggerSync(id, { entity: 'all', mode: 'delta' }),
    onSuccess: () => {
      toast.success('Senkronizasyon kuyruğa alındı');
      queryClient.invalidateQueries({ queryKey: ['erp', 'connections'] });
    },
    onError: () => toast.error('Senkronizasyon başlatılamadı'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => erpApi.deleteConnection(id),
    onSuccess: () => {
      toast.success('Bağlantı silindi');
      queryClient.invalidateQueries({ queryKey: ['erp', 'connections'] });
    },
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="ERP Entegrasyonu"
        description="Logo, Paraşüt ve SAP Business One bağlantılarını yönet."
        actions={
          <Button onClick={() => setShowCreate(true)}>
            <Plug className="w-4 h-4 mr-2" /> Yeni Bağlantı
          </Button>
        }
      />

      <Card>
        <div className="divide-y divide-gray-100 dark:divide-gray-800">
          {connectionsQuery.isLoading && (
            <div className="p-6 text-sm text-gray-500">Yükleniyor…</div>
          )}
          {connectionsQuery.isError && (
            <div className="p-6 text-sm text-red-600">
              Bağlantılar alınamadı. ERP modülü açık mı (FEATURE_ERP_CONNECTOR)?
            </div>
          )}
          {connectionsQuery.data?.length === 0 && (
            <div className="p-10 text-center">
              <Plug className="w-10 h-10 mx-auto text-gray-400" />
              <h3 className="mt-3 font-medium text-gray-900 dark:text-white">
                Henüz ERP bağlantısı yok
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                İlk bağlantıyı ekleyerek stok, fiyat ve müşteri senkronizasyonunu başlatın.
              </p>
            </div>
          )}
          {connectionsQuery.data?.map((row) => (
            <ConnectionRow
              key={row.id}
              connection={row}
              onTest={() => testMutation.mutate(row.id)}
              onSync={() => syncMutation.mutate(row.id)}
              onDelete={() => {
                if (confirm(`${row.name} bağlantısını silmek istiyor musunuz?`)) {
                  deleteMutation.mutate(row.id);
                }
              }}
              testing={testMutation.isPending && testMutation.variables === row.id}
              syncing={syncMutation.isPending && syncMutation.variables === row.id}
            />
          ))}
        </div>
      </Card>

      <TrustLayerNote />

      {showCreate && (
        <CreateConnectionModal
          onClose={() => setShowCreate(false)}
          onSubmit={(body) => createMutation.mutate(body)}
          submitting={createMutation.isPending}
        />
      )}
    </div>
  );
}

interface ConnectionRowProps {
  connection: ERPConnection;
  onTest: () => void;
  onSync: () => void;
  onDelete: () => void;
  testing: boolean;
  syncing: boolean;
}

function ConnectionRow({
  connection,
  onTest,
  onSync,
  onDelete,
  testing,
  syncing,
}: ConnectionRowProps) {
  const option = CONNECTOR_OPTIONS.find((opt) => opt.value === connection.type);
  return (
    <div className="p-5 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-lg bg-indigo-100 dark:bg-indigo-900/30 flex items-center justify-center">
          <Plug className="w-5 h-5 text-indigo-600 dark:text-indigo-300" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h3 className="font-medium text-gray-900 dark:text-white">{connection.name}</h3>
            {connection.is_active ? (
              <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300">
                <CheckCircle2 className="w-3 h-3" /> Aktif
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                <CircleSlash className="w-3 h-3" /> Pasif
              </span>
            )}
          </div>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {option?.label || connection.type} — {connection.endpoint}
          </p>
          <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-gray-500">
            <div>
              <dt className="inline font-medium">Müşteri:</dt>{' '}
              <dd className="inline">{formatRelative(connection.last_customer_sync_at)}</dd>
            </div>
            <div>
              <dt className="inline font-medium">Ürün:</dt>{' '}
              <dd className="inline">{formatRelative(connection.last_product_sync_at)}</dd>
            </div>
            {connection.sync_cron && (
              <div>
                <dt className="inline font-medium">Cron:</dt>{' '}
                <dd className="inline font-mono">{connection.sync_cron}</dd>
              </div>
            )}
          </dl>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={onTest} disabled={testing}>
          <ShieldCheck className="w-4 h-4 mr-1.5" />
          {testing ? 'Test ediliyor…' : 'Test'}
        </Button>
        <Button onClick={onSync} disabled={syncing}>
          <RefreshCw className={`w-4 h-4 mr-1.5 ${syncing ? 'animate-spin' : ''}`} />
          Sync
        </Button>
        <Link
          to={`/admin/erp/${connection.id}`}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
        >
          <Settings2 className="w-4 h-4" /> Detay
        </Link>
        <button
          type="button"
          onClick={onDelete}
          className="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg"
          aria-label="Bağlantıyı sil"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}

function TrustLayerNote() {
  return (
    <Card className="border-indigo-100 dark:border-indigo-900/40 bg-indigo-50/50 dark:bg-indigo-900/10">
      <div className="p-4 flex items-start gap-3">
        <TriangleAlert className="w-5 h-5 text-indigo-600 dark:text-indigo-300 flex-shrink-0 mt-0.5" />
        <div className="text-sm text-indigo-900 dark:text-indigo-100">
          <strong>Gizlilik:</strong> ERP kimlik bilgileri sunucuda Fernet (AES-128-GCM) ile
          şifrelenir. AI Trust Layer açıkken Claude API'ye gönderilen yazılar PII (TC, IBAN,
          e-posta, telefon) filtrelenerek yollanır.
        </div>
      </div>
    </Card>
  );
}

interface CreateConnectionModalProps {
  onClose: () => void;
  onSubmit: (body: ERPConnectionCreate) => void;
  submitting: boolean;
}

function CreateConnectionModal({ onClose, onSubmit, submitting }: CreateConnectionModalProps) {
  const [type, setType] = useState<ERPConnectionType>('parasut');
  const [name, setName] = useState('');
  const [endpoint, setEndpoint] = useState('');
  const [credsJson, setCredsJson] = useState(
    JSON.stringify(
      {
        client_id: '',
        client_secret: '',
        username: '',
        password: '',
        company_id: '',
      },
      null,
      2,
    ),
  );
  const [syncCron, setSyncCron] = useState('0 */2 * * *');
  const [error, setError] = useState<string | null>(null);

  const selected = CONNECTOR_OPTIONS.find((opt) => opt.value === type);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    let credentials: Record<string, unknown>;
    try {
      credentials = JSON.parse(credsJson);
    } catch {
      setError('Kimlik bilgileri geçerli JSON olmalı');
      return;
    }
    if (!name.trim() || !endpoint.trim()) {
      setError('Ad ve endpoint zorunlu');
      return;
    }
    onSubmit({
      type,
      name: name.trim(),
      endpoint: endpoint.trim(),
      credentials,
      sync_cron: syncCron.trim() || null,
    });
  }

  return (
    <Modal onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4 p-6 max-w-lg">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
          Yeni ERP Bağlantısı
        </h2>
        <p className="text-sm text-gray-500">
          Bağlantı sihirbazı kimlik bilgilerini şifreleyerek kaydeder. Şifreler hiçbir zaman
          tarayıcıda saklanmaz.
        </p>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
            ERP Tipi
          </label>
          <select
            value={type}
            onChange={(event) => setType(event.target.value as ERPConnectionType)}
            className="w-full rounded-lg border-gray-200 dark:border-gray-700 dark:bg-gray-900 text-sm"
          >
            {CONNECTOR_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          {selected && (
            <p className="mt-1 text-xs text-gray-500">{selected.hint}</p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
            İsim
          </label>
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Ör. Logo Tiger Prod"
            className="w-full rounded-lg border-gray-200 dark:border-gray-700 dark:bg-gray-900 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
            Endpoint URL
          </label>
          <input
            type="url"
            value={endpoint}
            onChange={(event) => setEndpoint(event.target.value)}
            placeholder="https://api.parasut.com/v4"
            className="w-full rounded-lg border-gray-200 dark:border-gray-700 dark:bg-gray-900 text-sm"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
            Kimlik Bilgileri (JSON)
          </label>
          <textarea
            value={credsJson}
            onChange={(event) => setCredsJson(event.target.value)}
            rows={8}
            spellCheck={false}
            className="w-full rounded-lg border-gray-200 dark:border-gray-700 dark:bg-gray-900 font-mono text-xs"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
            Zamanlama (cron) — opsiyonel
          </label>
          <input
            type="text"
            value={syncCron}
            onChange={(event) => setSyncCron(event.target.value)}
            placeholder="0 */2 * * *"
            className="w-full rounded-lg border-gray-200 dark:border-gray-700 dark:bg-gray-900 font-mono text-xs"
          />
        </div>

        {error && <div className="text-sm text-red-600">{error}</div>}

        <div className="flex gap-2 justify-end pt-2">
          <Button variant="secondary" type="button" onClick={onClose}>
            Vazgeç
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? 'Kaydediliyor…' : 'Kaydet'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
