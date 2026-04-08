import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { boardApi } from '../../lib/api';
import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';
// Badge not used — inline stage pills instead
import { formatCurrency } from '../../lib/formatters';
import type { KanbanColumn, BoardSummary, Opportunity } from '../../lib/types';

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

function KanbanCard({ opp }: { opp: Opportunity }) {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate(`/opportunities/${opp.id}`)}
      className="w-full rounded-lg border border-gray-200 bg-white p-3 text-left shadow-sm hover:shadow-md transition-shadow dark:border-gray-700 dark:bg-gray-800"
    >
      <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">{opp.title}</p>
      {opp.customer && (
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 truncate">{opp.customer.name}</p>
      )}
      <div className="mt-2 flex items-center justify-between">
        {opp.amount != null ? (
          <span className="text-sm font-bold text-gray-800 dark:text-gray-200">
            {formatCurrency(opp.amount, opp.currency)}
          </span>
        ) : (
          <span className="text-xs text-gray-400">-</span>
        )}
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
  const { data: kanban, isLoading } = useQuery<{ columns: KanbanColumn[] }>({
    queryKey: ['board', 'kanban'],
    queryFn: () => boardApi.getKanban(),
  });

  const { data: summary } = useQuery<BoardSummary>({
    queryKey: ['board', 'summary'],
    queryFn: () => boardApi.getSummary(30),
  });

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

      {/* KPI bar */}
      {summary && (
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Card>
            <div className="p-4 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">Acik Pipeline</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">
                {formatCurrency(summary.open_pipeline_total, 'TRY')}
              </p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">Kazanma Orani</p>
              <p className="text-xl font-bold text-green-600">%{summary.win_rate}</p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">Kazanilan</p>
              <p className="text-xl font-bold text-gray-900 dark:text-white">{summary.won_count}</p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-xs text-gray-500 dark:text-gray-400">Cururyen (Rotting)</p>
              <p className={`text-xl font-bold ${summary.rotting_count > 0 ? 'text-red-600' : 'text-gray-900 dark:text-white'}`}>
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
                <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STAGE_COLORS[col.stage] || 'bg-gray-100 text-gray-700'}`}>
                  {STAGE_LABELS[col.stage] || col.stage}
                </span>
                <span className="text-xs font-medium text-gray-500">{col.count}</span>
              </div>
              <span className="text-xs font-semibold text-gray-500 dark:text-gray-400">
                {formatCurrency(col.total_amount, 'TRY')}
              </span>
            </div>
            <div className="space-y-2 rounded-xl bg-gray-50 p-2 dark:bg-gray-900/50 min-h-[200px]">
              {col.items.length === 0 ? (
                <p className="py-8 text-center text-xs text-gray-400">Firsat yok</p>
              ) : (
                col.items.map((opp) => <KanbanCard key={opp.id} opp={opp} />)
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
