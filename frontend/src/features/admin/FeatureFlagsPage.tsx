import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { AlertTriangle, Flag, RotateCcw, Search } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { featureFlagsApi, type FeatureFlagRow } from '../../lib/api';

type EffectiveFilter = 'all' | 'on' | 'off' | 'override';

export function FeatureFlagsPage() {
  const queryClient = useQueryClient();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<EffectiveFilter>('all');

  const flagsQuery = useQuery({
    queryKey: ['admin', 'feature-flags'],
    queryFn: () => featureFlagsApi.list(),
    refetchInterval: 30_000,
  });

  const patchMutation = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean | null }) =>
      featureFlagsApi.setOverride(name, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'feature-flags'] });
    },
    onError: (err: unknown) => {
      toast.error(err instanceof Error ? err.message : 'Güncellenemedi');
    },
  });

  const clearMutation = useMutation({
    mutationFn: () => featureFlagsApi.clearAll(),
    onSuccess: () => {
      toast.success('Tüm override temizlendi, env değerlerine dönüldü');
      queryClient.invalidateQueries({ queryKey: ['admin', 'feature-flags'] });
    },
  });

  const rows = useMemo(() => {
    const data = flagsQuery.data ?? [];
    return data
      .filter((row) => row.name.toLowerCase().includes(query.toLowerCase()))
      .filter((row) => {
        if (filter === 'on') return row.effective;
        if (filter === 'off') return !row.effective;
        if (filter === 'override') return row.override !== null;
        return true;
      });
  }, [flagsQuery.data, query, filter]);

  const totals = useMemo(() => {
    const data = flagsQuery.data ?? [];
    return {
      total: data.length,
      on: data.filter((r) => r.effective).length,
      override: data.filter((r) => r.override !== null).length,
    };
  }, [flagsQuery.data]);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Özellik Bayrakları"
        description="Pilot rollout sırasında FEATURE_* bayraklarını restart olmadan değiştir."
        actions={
          <Button
            variant="secondary"
            disabled={clearMutation.isPending || totals.override === 0}
            onClick={() => {
              if (confirm('Tüm override değerleri silinecek — env değerlerine dönülsün mü?')) {
                clearMutation.mutate();
              }
            }}
          >
            <RotateCcw className="w-4 h-4 mr-1.5" />
            Tüm Override Temizle
          </Button>
        }
      />

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <SummaryCard label="Toplam bayrak" value={totals.total} icon={<Flag className="w-5 h-5" />} />
        <SummaryCard label="Aktif" value={totals.on} accent="text-green-600" />
        <SummaryCard
          label="Override var"
          value={totals.override}
          accent="text-amber-600"
          icon={totals.override > 0 ? <AlertTriangle className="w-5 h-5" /> : undefined}
        />
      </div>

      <Card>
        <div className="p-4 border-b border-gray-100 dark:border-gray-800 flex flex-wrap gap-3 items-center">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="FEATURE_ adı ile ara…"
              className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border-gray-200 dark:border-gray-700 dark:bg-gray-900"
            />
          </div>
          <div className="flex gap-1 bg-gray-100 dark:bg-gray-900 rounded-lg p-1">
            {([
              ['all', 'Tümü'],
              ['on', 'Açık'],
              ['off', 'Kapalı'],
              ['override', 'Override'],
            ] as [EffectiveFilter, string][]).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value)}
                className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                  filter === value
                    ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                    : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="divide-y divide-gray-100 dark:divide-gray-800">
          {flagsQuery.isLoading && <div className="p-6 text-sm text-gray-500">Yükleniyor…</div>}
          {flagsQuery.isError && (
            <div className="p-6 text-sm text-red-600">
              Bayraklar alınamadı. Sadece sales_manager rolü bu sayfaya erişebilir.
            </div>
          )}
          {rows.length === 0 && !flagsQuery.isLoading && (
            <div className="p-6 text-sm text-gray-500">Filtreye uyan bayrak yok.</div>
          )}
          {rows.map((row) => (
            <FlagRow
              key={row.name}
              row={row}
              onToggle={(value) => patchMutation.mutate({ name: row.name, enabled: value })}
              onClear={() => patchMutation.mutate({ name: row.name, enabled: null })}
              busy={patchMutation.isPending && patchMutation.variables?.name === row.name}
            />
          ))}
        </div>
      </Card>
    </div>
  );
}

interface FlagRowProps {
  row: FeatureFlagRow;
  onToggle: (enabled: boolean) => void;
  onClear: () => void;
  busy: boolean;
}

function FlagRow({ row, onToggle, onClear, busy }: FlagRowProps) {
  const overrideActive = row.override !== null;
  return (
    <div className="p-4 flex flex-col md:flex-row md:items-center gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <code className="text-sm font-mono font-semibold text-gray-900 dark:text-white">
            {row.name}
          </code>
          <Pill label={row.effective ? 'Açık' : 'Kapalı'} tone={row.effective ? 'green' : 'gray'} />
          {overrideActive && (
            <Pill label={`Override: ${row.override ? 'Açık' : 'Kapalı'}`} tone="amber" />
          )}
          <span className="text-xs text-gray-500">
            env: {row.env_value ? 'true' : 'false'} · default: {row.default ? 'true' : 'false'}
          </span>
        </div>
        {row.description && (
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{row.description}</p>
        )}
      </div>
      <div className="flex gap-2">
        <Button
          variant="secondary"
          onClick={() => onToggle(true)}
          disabled={busy || row.override === true}
          className={row.override === true ? '!bg-green-600 !text-white' : ''}
        >
          Aç
        </Button>
        <Button
          variant="secondary"
          onClick={() => onToggle(false)}
          disabled={busy || row.override === false}
          className={row.override === false ? '!bg-red-600 !text-white' : ''}
        >
          Kapat
        </Button>
        <Button
          variant="secondary"
          onClick={onClear}
          disabled={busy || !overrideActive}
        >
          Env'e dön
        </Button>
      </div>
    </div>
  );
}

function SummaryCard({
  label,
  value,
  accent,
  icon,
}: {
  label: string;
  value: number;
  accent?: string;
  icon?: React.ReactNode;
}) {
  return (
    <Card>
      <div className="p-4 flex items-center gap-3">
        {icon && <div className="text-gray-400">{icon}</div>}
        <div>
          <div className={`text-2xl font-semibold tabular-nums ${accent ?? ''}`}>{value}</div>
          <div className="text-xs text-gray-500">{label}</div>
        </div>
      </div>
    </Card>
  );
}

function Pill({ label, tone }: { label: string; tone: 'green' | 'gray' | 'amber' }) {
  const classes: Record<string, string> = {
    green: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
    gray: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
    amber: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  };
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-medium ${classes[tone]}`}>
      {label}
    </span>
  );
}
