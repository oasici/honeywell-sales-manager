import { useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowLeft, ChevronRight, RefreshCw } from 'lucide-react';

import { PageHeader } from '../../../components/ui/PageHeader';
import { Card } from '../../../components/ui/Card';
import { Button } from '../../../components/ui/Button';
import { erpApi, type ERPConflict, type ERPMappingRow, type ERPSyncJob } from '../../../lib/api';

type Tab = 'jobs' | 'mappings' | 'conflicts';

export function ERPConnectionDetailPage() {
  const params = useParams<{ id: string }>();
  const connectionId = Number(params.id);
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>('jobs');

  const connectionQuery = useQuery({
    queryKey: ['erp', 'connection', connectionId],
    queryFn: () => erpApi.getConnection(connectionId),
    enabled: Number.isFinite(connectionId),
  });

  const jobsQuery = useQuery({
    queryKey: ['erp', 'jobs', connectionId],
    queryFn: () => erpApi.listJobs(connectionId, 30),
    enabled: Number.isFinite(connectionId),
    refetchInterval: 10_000,
  });

  const mappingsQuery = useQuery({
    queryKey: ['erp', 'mappings', connectionId],
    queryFn: () => erpApi.listMappings(connectionId, undefined, 200),
    enabled: Number.isFinite(connectionId) && tab === 'mappings',
  });

  const conflictsQuery = useQuery({
    queryKey: ['erp', 'conflicts'],
    queryFn: () => erpApi.listConflicts('pending', 100),
    enabled: tab === 'conflicts',
  });

  const syncMutation = useMutation({
    mutationFn: (body: { entity: string; mode: 'full' | 'delta' }) =>
      erpApi.triggerSync(connectionId, body),
    onSuccess: () => {
      toast.success('Sync kuyruğa alındı');
      queryClient.invalidateQueries({ queryKey: ['erp', 'jobs', connectionId] });
    },
    onError: () => toast.error('Sync başlatılamadı'),
  });

  if (!Number.isFinite(connectionId)) {
    return <div className="p-6 text-sm text-red-600">Geçersiz bağlantı id</div>;
  }

  return (
    <div className="space-y-6">
      <Link
        to="/admin/erp"
        className="inline-flex items-center text-sm text-gray-500 hover:text-gray-700"
      >
        <ArrowLeft className="w-4 h-4 mr-1" /> ERP Bağlantıları
      </Link>

      <PageHeader
        title={connectionQuery.data?.name ?? 'ERP Bağlantısı'}
        description={`${connectionQuery.data?.type?.toUpperCase() ?? '—'} • ${
          connectionQuery.data?.endpoint ?? ''
        }`}
        actions={
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => syncMutation.mutate({ entity: 'all', mode: 'delta' })}
              disabled={syncMutation.isPending}
            >
              <RefreshCw
                className={`w-4 h-4 mr-1.5 ${syncMutation.isPending ? 'animate-spin' : ''}`}
              />
              Delta Sync
            </Button>
            <Button
              onClick={() => syncMutation.mutate({ entity: 'all', mode: 'full' })}
              disabled={syncMutation.isPending}
            >
              Tam Sync
            </Button>
          </div>
        }
      />

      <div className="flex gap-2 bg-gray-100 dark:bg-gray-900 rounded-lg p-1 w-fit">
        <TabButton label="İş Kuyruğu" active={tab === 'jobs'} onClick={() => setTab('jobs')} />
        <TabButton
          label="Eşlemeler"
          active={tab === 'mappings'}
          onClick={() => setTab('mappings')}
        />
        <TabButton
          label="Çakışmalar"
          active={tab === 'conflicts'}
          onClick={() => setTab('conflicts')}
        />
      </div>

      {tab === 'jobs' && <JobsTable jobs={jobsQuery.data ?? []} loading={jobsQuery.isLoading} />}
      {tab === 'mappings' && (
        <MappingsTable mappings={mappingsQuery.data ?? []} loading={mappingsQuery.isLoading} />
      )}
      {tab === 'conflicts' && (
        <ConflictsTable
          connectionId={connectionId}
          conflicts={conflictsQuery.data ?? []}
          loading={conflictsQuery.isLoading}
        />
      )}
    </div>
  );
}

function TabButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
        active
          ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
          : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-200'
      }`}
    >
      {label}
    </button>
  );
}

function JobsTable({ jobs, loading }: { jobs: ERPSyncJob[]; loading: boolean }) {
  return (
    <Card>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-900/60">
            <tr className="text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-4 py-2">ID</th>
              <th className="px-4 py-2">Varlık</th>
              <th className="px-4 py-2">Mod</th>
              <th className="px-4 py-2">Durum</th>
              <th className="px-4 py-2">Kuyruk</th>
              <th className="px-4 py-2 text-right">Eklendi/Güncellendi</th>
              <th className="px-4 py-2">Hata</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {loading && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-gray-500">
                  Yükleniyor…
                </td>
              </tr>
            )}
            {!loading && jobs.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-gray-500">
                  Henüz sync kaydı yok — sağ üstten tetikleyin.
                </td>
              </tr>
            )}
            {jobs.map((job) => (
              <tr key={job.id}>
                <td className="px-4 py-2 font-mono text-xs">{job.id}</td>
                <td className="px-4 py-2">{job.entity}</td>
                <td className="px-4 py-2 uppercase text-xs">{job.mode}</td>
                <td className="px-4 py-2">
                  <StatusPill status={job.status} />
                </td>
                <td className="px-4 py-2 text-xs text-gray-500">
                  {new Date(job.queued_at).toLocaleString('tr-TR')}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {job.records_created}+ / {job.records_updated}↻ / {job.records_failed}✗
                </td>
                <td className="px-4 py-2 text-xs text-red-600 max-w-xs truncate">
                  {job.error_message ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function StatusPill({ status }: { status: ERPSyncJob['status'] }) {
  const classes: Record<string, string> = {
    queued: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
    running: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
    success: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
    failed: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
    partial: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  };
  return (
    <span
      className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${
        classes[status] ?? classes.queued
      }`}
    >
      {status}
    </span>
  );
}

function MappingsTable({
  mappings,
  loading,
}: {
  mappings: ERPMappingRow[];
  loading: boolean;
}) {
  return (
    <Card>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-900/60">
            <tr className="text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-4 py-2">ID</th>
              <th className="px-4 py-2">Varlık</th>
              <th className="px-4 py-2">HSS ID</th>
              <th className="px-4 py-2">ERP ID</th>
              <th className="px-4 py-2">Son Kaynak</th>
              <th className="px-4 py-2">Son Sync</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {loading && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-gray-500">
                  Yükleniyor…
                </td>
              </tr>
            )}
            {!loading && mappings.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-gray-500">
                  Henüz eşleme yok.
                </td>
              </tr>
            )}
            {mappings.map((row) => (
              <tr key={row.id}>
                <td className="px-4 py-2 font-mono text-xs">{row.id}</td>
                <td className="px-4 py-2">{row.entity_type}</td>
                <td className="px-4 py-2 font-mono">{row.internal_id}</td>
                <td className="px-4 py-2 font-mono">{row.external_id}</td>
                <td className="px-4 py-2 uppercase text-xs">{row.last_source}</td>
                <td className="px-4 py-2 text-xs text-gray-500">
                  {new Date(row.last_synced_at).toLocaleString('tr-TR')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function ConflictsTable({
  connectionId,
  conflicts,
  loading,
}: {
  connectionId: number;
  conflicts: ERPConflict[];
  loading: boolean;
}) {
  const queryClient = useQueryClient();
  const resolveMutation = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'hss_wins' | 'erp_wins' | 'dismiss' }) =>
      erpApi.resolveConflict(id, { action }),
    onSuccess: () => {
      toast.success('Çakışma çözüldü');
      queryClient.invalidateQueries({ queryKey: ['erp', 'conflicts'] });
    },
  });

  const filtered = conflicts.filter((c) => c.connection_id === connectionId);

  return (
    <Card>
      <div className="divide-y divide-gray-100 dark:divide-gray-800">
        {loading && <div className="p-6 text-sm text-gray-500">Yükleniyor…</div>}
        {!loading && filtered.length === 0 && (
          <div className="p-8 text-center text-sm text-gray-500">
            Bekleyen çakışma yok. İki tarafta aynı anda değişen bir kayıt görülürse burada listelenir.
          </div>
        )}
        {filtered.map((conflict) => {
          const diffs = safeParse<Array<{ field: string; hss: unknown; erp: unknown }>>(
            conflict.field_diffs,
            [],
          );
          return (
            <div key={conflict.id} className="p-4 space-y-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-medium text-gray-900 dark:text-white">
                  {conflict.entity_type.toUpperCase()}
                </span>
                <ChevronRight className="w-4 h-4 text-gray-400" />
                <span className="font-mono text-xs">HSS #{conflict.internal_id}</span>
                <ChevronRight className="w-4 h-4 text-gray-400" />
                <span className="font-mono text-xs">ERP {conflict.external_id}</span>
                <span className="ml-auto text-xs text-gray-500">
                  {new Date(conflict.detected_at).toLocaleString('tr-TR')}
                </span>
              </div>
              {diffs.length > 0 && (
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-left text-gray-500">
                      <th className="pr-4">Alan</th>
                      <th className="pr-4">HSS</th>
                      <th>ERP</th>
                    </tr>
                  </thead>
                  <tbody>
                    {diffs.map((diff) => (
                      <tr key={diff.field} className="border-t border-dashed border-gray-200">
                        <td className="py-1 pr-4 font-mono">{diff.field}</td>
                        <td className="py-1 pr-4">{String(diff.hss ?? '—')}</td>
                        <td className="py-1">{String(diff.erp ?? '—')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  onClick={() =>
                    resolveMutation.mutate({ id: conflict.id, action: 'hss_wins' })
                  }
                >
                  HSS Kazansın
                </Button>
                <Button
                  onClick={() =>
                    resolveMutation.mutate({ id: conflict.id, action: 'erp_wins' })
                  }
                >
                  ERP Kazansın
                </Button>
                <Button
                  variant="secondary"
                  onClick={() =>
                    resolveMutation.mutate({ id: conflict.id, action: 'dismiss' })
                  }
                >
                  Yoksay
                </Button>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function safeParse<T>(value: string, fallback: T): T {
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}
