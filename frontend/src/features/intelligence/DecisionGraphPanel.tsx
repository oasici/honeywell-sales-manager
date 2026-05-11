import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { CheckCircle2, CircleDot, AlertTriangle, Circle, PlayCircle, Sparkles } from 'lucide-react';
import { toast } from 'sonner';

import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { decisionGraphApi } from '../../lib/api';
import { onDecisionGraphChanged } from '../../lib/cacheInvalidation';

/**
 * S-C — decision graph viewer.
 * Renders the structural process graph for one opportunity. Manager can
 * advance node states (not_started → in_progress → complete | blocked).
 */
interface DecisionGraphPanelProps {
  opportunityId: number;
}

const STATE_BADGE: Record<
  string,
  { variant: 'success' | 'warning' | 'info' | 'default' | 'danger'; label: string }
> = {
  complete: { variant: 'success', label: 'Tamamlandı' },
  in_progress: { variant: 'info', label: 'Sürüyor' },
  blocked: { variant: 'danger', label: 'Engelli' },
  skipped: { variant: 'default', label: 'Atlandı' },
  not_started: { variant: 'default', label: 'Başlamadı' },
};

const STATE_ICON: Record<string, React.ReactNode> = {
  complete: <CheckCircle2 className="h-4 w-4 text-success" />,
  in_progress: <CircleDot className="h-4 w-4 text-info" />,
  blocked: <AlertTriangle className="h-4 w-4 text-warning" />,
  skipped: <Circle className="h-4 w-4 text-slate-400" />,
  not_started: <Circle className="h-4 w-4 text-slate-300" />,
};

export function DecisionGraphPanel({ opportunityId }: DecisionGraphPanelProps) {
  const qc = useQueryClient();
  const [actingNodeId, setActingNodeId] = useState<number | null>(null);

  const graphQuery = useQuery({
    queryKey: ['decision-graph', opportunityId],
    queryFn: () => decisionGraphApi.get(opportunityId),
    enabled: opportunityId > 0,
  });

  const initMutation = useMutation({
    mutationFn: () => decisionGraphApi.initialize(opportunityId),
    onSuccess: () => {
      toast.success('Karar grafı oluşturuldu');
      onDecisionGraphChanged(qc, opportunityId);
    },
    onError: () => toast.error('Graf oluşturulamadı'),
  });

  const patchMutation = useMutation({
    mutationFn: ({ nodeId, state }: { nodeId: number; state: string }) =>
      decisionGraphApi.patchNode(opportunityId, nodeId, { state }),
    onSuccess: () => {
      // Round-8 R8-CACHE-6 — fan out to deal-risk + decision-gap consumers.
      onDecisionGraphChanged(qc, opportunityId);
    },
    onSettled: () => setActingNodeId(null),
  });

  const graph = graphQuery.data;

  if (graphQuery.isLoading) {
    return (
      <Card title="Karar süreci">
        <Skeleton className="h-32" />
      </Card>
    );
  }

  // Round-8 R8-EMPTY-1 — distinguish "graph never created" from
  // "graph exists but is mid-initialization".
  if (!graph) {
    return (
      <Card
        title="Karar süreci"
        description="Bütçe / hukuk / tedarik / güvenlik adımlarının durumu"
      >
        <div className="flex flex-col items-center gap-3 py-6">
          <Sparkles className="h-8 w-8 text-slate-400" />
          <p className="text-caption text-slate-500">
            Bu fırsat için karar grafı henüz oluşturulmadı.
          </p>
          <Button
            variant="primary"
            size="sm"
            onClick={() => initMutation.mutate()}
            disabled={initMutation.isPending}
          >
            <PlayCircle className="mr-1 h-3 w-3" />
            Varsayılan grafı oluştur
          </Button>
        </div>
      </Card>
    );
  }

  // Round-8 R8-EMPTY-1 — graph row exists but no nodes yet (in-flight init).
  if (graph.nodes.length === 0) {
    return (
      <Card title="Karar süreci">
        <div className="flex flex-col items-center gap-3 py-6">
          <Skeleton className="h-3 w-32" />
          <p className="text-caption text-slate-500">Grafı hazırlanıyor...</p>
        </div>
      </Card>
    );
  }

  const progressPct = Math.round((graph.progress?.ratio ?? 0) * 100);

  return (
    <Card
      title="Karar süreci"
      description={`${graph.progress.complete}/${graph.progress.total} adım tamamlandı`}
      action={
        <Badge variant={progressPct >= 75 ? 'success' : progressPct >= 30 ? 'info' : 'warning'}>
          {progressPct}%
        </Badge>
      }
    >
      <ul className="divide-y divide-slate-100">
        {graph.nodes.map((node) => {
          // Round-10 R10-FE-13 — `not_started` always defined.
          const badge = STATE_BADGE[node.state] ?? STATE_BADGE.not_started!;
          return (
            <li key={node.id} className="flex items-start justify-between gap-3 py-3">
              <div className="flex items-start gap-2 min-w-0">
                <div className="mt-0.5">{STATE_ICON[node.state] ?? STATE_ICON.not_started}</div>
                <div className="min-w-0">
                  <div className="text-body-strong text-slate-800">{node.label}</div>
                  <div className="mt-0.5 flex items-center gap-2">
                    <Badge variant={badge.variant}>{badge.label}</Badge>
                    {node.blocker_reason && (
                      <span className="text-caption text-warning">{node.blocker_reason}</span>
                    )}
                  </div>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1">
                {node.state !== 'in_progress' && (
                  <Button
                    variant="tertiary"
                    size="sm"
                    onClick={() => {
                      setActingNodeId(node.id);
                      patchMutation.mutate({ nodeId: node.id, state: 'in_progress' });
                    }}
                    disabled={patchMutation.isPending && actingNodeId === node.id}
                  >
                    Başlat
                  </Button>
                )}
                {node.state !== 'complete' && (
                  <Button
                    variant="tertiary"
                    size="sm"
                    onClick={() => {
                      setActingNodeId(node.id);
                      patchMutation.mutate({ nodeId: node.id, state: 'complete' });
                    }}
                    disabled={patchMutation.isPending && actingNodeId === node.id}
                  >
                    Bitir
                  </Button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

export default DecisionGraphPanel;
