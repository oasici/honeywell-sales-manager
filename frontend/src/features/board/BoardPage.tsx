import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { boardApi, dealHealthApi, pipelinesApi } from '../../lib/api';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';
import { DealHealthBadge } from './DealHealthBadge';
import { formatCurrency } from '../../lib/formatters';
import type {
  KanbanColumn,
  BoardSummary,
  Opportunity,
  DealHealthReport,
  Pipeline,
} from '../../lib/types';

const STAGE_LABELS: Record<string, string> = {
  prospecting: 'Arastirma',
  qualified: 'Nitelenmis',
  proposal: 'Teklif',
  negotiation: 'Muzakere',
  closed_won: 'Kazanildi',
  closed_lost: 'Kaybedildi',
};

const STAGE_COLORS: Record<string, string> = {
  prospecting: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
  qualified: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/30 dark:text-indigo-300',
  proposal: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300',
  negotiation: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
  closed_won: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
  closed_lost: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300',
};

interface KanbanCardProps {
  opp: Opportunity;
  healthScore?: { score: number; risk_level: string } | null;
}

function KanbanCard({ opp, healthScore }: KanbanCardProps) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate(`/opportunities/${opp.id}`)}
      className="w-full rounded-lg border border-gray-200 bg-white p-3 text-left shadow-sm hover:shadow-md transition-shadow dark:border-gray-700 dark:bg-gray-800"
    >
      <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{opp.title}</p>
      {opp.customer && (
        <p className="mt-0.5 text-xs font-medium text-gray-600 dark:text-gray-300 truncate">
          {opp.customer.name}
        </p>
      )}
      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          {opp.amount != null ? (
            <span className="text-sm font-bold text-gray-800 dark:text-gray-200">
              {formatCurrency(opp.amount, opp.currency)}
            </span>
          ) : (
            <span className="text-xs text-gray-400">-</span>
          )}
          {healthScore && (
            <DealHealthBadge score={healthScore.score} riskLevel={healthScore.risk_level} />
          )}
        </div>
        {opp.rotting_days > 7 && (
          <span className="text-[10px] font-medium text-red-600 dark:text-red-400">
            {opp.rotting_days}g
          </span>
        )}
      </div>
      {opp.owner && (
        <p className="mt-1 text-[10px] text-gray-400 truncate">{opp.owner.full_name}</p>
      )}
    </button>
  );
}

export default function BoardPage() {
  const [selectedPipelineId, setSelectedPipelineId] = useState<number | null>(null);

  const { data: pipelines = [] } = useQuery<Pipeline[]>({
    queryKey: ['pipelines'],
    queryFn: async () => {
      const res = await pipelinesApi.list();
      return res?.pipelines ?? res?.items ?? (Array.isArray(res) ? res : []);
    },
  });

  // Derive the active pipeline: user selection → default → first available
  const activePipelineId =
    selectedPipelineId ?? pipelines.find((p) => p.is_default)?.id ?? pipelines[0]?.id ?? null;

  const { data: kanban, isLoading } = useQuery<{ columns: KanbanColumn[] }>({
    queryKey: ['board', 'kanban', activePipelineId],
    queryFn: () =>
      boardApi.getKanban(activePipelineId != null ? { pipeline_id: activePipelineId } : undefined),
  });

  const { data: summary } = useQuery<BoardSummary>({
    queryKey: ['board', 'summary'],
    queryFn: () => boardApi.getSummary(30),
  });

  const { data: healthOverview } = useQuery<{ opportunities: DealHealthReport[] }>({
    queryKey: ['deal-health', 'overview'],
    queryFn: () => dealHealthApi.getOverview(),
    retry: false,
    staleTime: 60_000,
  });

  const healthMap = useMemo(() => {
    const map = new Map<number, { score: number; risk_level: string }>();
    if (healthOverview?.opportunities) {
      for (const deal of healthOverview.opportunities) {
        map.set(deal.opportunity_id, {
          score: deal.score,
          risk_level: deal.risk_level,
        });
      }
    }
    return map;
  }, [healthOverview]);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton variant="card" count={3} />
      </div>
    );
  }

  const columns = kanban?.columns || [];

  return (
    <div>
      <PageHeader title="Sales Board" description="Pipeline gorunumu" />

      {/* Pipeline selector — only shown when multiple pipelines exist */}
      {pipelines.length > 1 && (
        <div className="mb-4 flex flex-wrap items-center gap-2">
          {pipelines.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setSelectedPipelineId(p.id)}
              className={`rounded-xl px-3 py-1.5 text-sm font-medium transition-colors ${
                activePipelineId === p.id
                  ? 'bg-blue-600 text-white shadow-sm'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:hover:bg-gray-700'
              }`}
            >
              {p.name}
              {p.is_default && <span className="ml-1.5 text-[10px] opacity-70">★</span>}
            </button>
          ))}
        </div>
      )}

      {/* KPI bar */}
      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                Acik Pipeline
              </p>
              <p className="mt-1 text-2xl font-extrabold text-blue-700 dark:text-blue-400">
                {formatCurrency(summary.open_pipeline_total, 'TRY')}
              </p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                Kazanma Orani
              </p>
              <p className="mt-1 text-2xl font-extrabold text-green-700 dark:text-green-400">
                %{summary.win_rate}
              </p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">Kazanilan</p>
              <p className="mt-1 text-2xl font-extrabold text-gray-900 dark:text-white">
                {summary.won_count}
              </p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm font-semibold text-gray-700 dark:text-gray-200">
                Curume (Rotting)
              </p>
              <p
                className={`mt-1 text-2xl font-extrabold ${summary.rotting_count > 0 ? 'text-red-700 dark:text-red-400' : 'text-gray-900 dark:text-white'}`}
              >
                {summary.rotting_count}
              </p>
            </div>
          </Card>
        </div>
      )}

      {/* Kanban board */}
      <div className="flex gap-4 overflow-x-auto pb-4">
        {columns.map((col) => (
          <div key={col.stage} className="min-w-[280px] shrink-0">
            <div className="mb-3 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-bold ${STAGE_COLORS[col.stage] || 'bg-gray-200 text-gray-800'}`}
                >
                  {STAGE_LABELS[col.stage] || col.stage}
                </span>
                <span className="rounded-full bg-gray-200 px-2 py-0.5 text-xs font-bold text-gray-800 dark:bg-gray-700 dark:text-gray-200">
                  {col.count}
                </span>
              </div>
              <span className="text-xs font-bold text-gray-700 dark:text-gray-300">
                {formatCurrency(col.total_amount, 'TRY')}
              </span>
            </div>
            <div className="space-y-2 rounded-xl bg-gray-50 p-2 dark:bg-gray-900/50 min-h-[200px]">
              {col.items.length === 0 ? (
                <p className="py-8 text-center text-xs text-gray-400">Firsat yok</p>
              ) : (
                col.items.map((opp) => (
                  <KanbanCard key={opp.id} opp={opp} healthScore={healthMap.get(opp.id) ?? null} />
                ))
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
