import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Network, RefreshCw, User as UserIcon, Users, Briefcase } from 'lucide-react';
import { toast } from 'sonner';

import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { relationshipsApi } from '../../lib/api';
import { onRelationshipMetricChanged, onRelationshipsRebuilt } from '../../lib/cacheInvalidation';

/**
 * S-B — relationship panel.
 * Surfaces strongest connections + coverage score for an opportunity or
 * an account / customer.
 */
interface RelationshipPanelProps {
  kind: 'opportunity' | 'account' | 'stakeholder' | 'user';
  entityId: number;
  /** Show the rebuild button (opportunity only). */
  allowRebuild?: boolean;
}

const KIND_ICON: Record<string, React.ReactNode> = {
  user: <UserIcon className="h-3.5 w-3.5" />,
  stakeholder: <Users className="h-3.5 w-3.5" />,
  account: <Briefcase className="h-3.5 w-3.5" />,
  opportunity: <Network className="h-3.5 w-3.5" />,
};

export function RelationshipPanel({
  kind,
  entityId,
  allowRebuild = false,
}: RelationshipPanelProps) {
  const qc = useQueryClient();

  const scoreQuery = useQuery({
    queryKey: ['relationship-score', kind, entityId],
    queryFn: () => relationshipsApi.score(kind, entityId),
    enabled: entityId > 0,
  });

  const strongestQuery = useQuery({
    queryKey: ['relationship-strongest', kind, entityId],
    queryFn: () => relationshipsApi.strongest(kind, entityId, 5),
    enabled: entityId > 0,
  });

  const rebuildMutation = useMutation({
    mutationFn: () => relationshipsApi.rebuildOpportunity(entityId),
    onSuccess: (data) => {
      toast.success(`${data.edges_touched} ilişki güncellendi`);
      // Round-8 R8-CACHE-7 — fan out to coverage-driven cards.
      if (kind === 'opportunity') {
        onRelationshipsRebuilt(qc, entityId);
      } else {
        onRelationshipMetricChanged(qc, kind, entityId);
      }
    },
    onError: () => toast.error('İlişki grafı yeniden oluşturulamadı'),
  });

  const score = scoreQuery.data;
  const items = strongestQuery.data?.items ?? [];

  return (
    <Card
      title="İlişki ağı"
      description={
        score
          ? `${score.edge_count} bağlantı · kapsama %${score.coverage_score.toFixed(0)}`
          : 'Bu kaydın bağlantı haritası'
      }
      action={
        allowRebuild && kind === 'opportunity' ? (
          <Button
            variant="tertiary"
            size="sm"
            onClick={() => rebuildMutation.mutate()}
            disabled={rebuildMutation.isPending}
          >
            <RefreshCw
              className={`mr-1 h-3 w-3 ${rebuildMutation.isPending ? 'animate-spin' : ''}`}
            />
            Yeniden hesapla
          </Button>
        ) : undefined
      }
    >
      {(scoreQuery.isLoading || strongestQuery.isLoading) && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      )}

      {!scoreQuery.isLoading && score && (
        <div className="grid grid-cols-3 gap-3 rounded-lg bg-slate-50 p-3">
          <div>
            <div className="text-caption text-slate-500">En güçlü</div>
            <div className="text-body-strong tabular-nums">
              {score.strongest_strength.toFixed(0)}
            </div>
          </div>
          <div>
            <div className="text-caption text-slate-500">Ortalama</div>
            <div className="text-body-strong tabular-nums">{score.avg_strength.toFixed(0)}</div>
          </div>
          <div>
            <div className="text-caption text-slate-500">Bağlantı</div>
            <div className="text-body-strong tabular-nums">{score.edge_count}</div>
          </div>
        </div>
      )}

      {!strongestQuery.isLoading && items.length === 0 && (
        <EmptyState
          title="Henüz bağlantı yok"
          description={
            allowRebuild
              ? 'Yeniden hesapla butonu ile etkinlik kaydından çıkar.'
              : 'Aktivite üretildikçe bağlantılar gözükecek.'
          }
          variant="compact"
        />
      )}

      {!strongestQuery.isLoading && items.length > 0 && (
        <ul className="mt-3 divide-y divide-slate-100">
          {items.map((edge, idx) => {
            const otherKind =
              edge.from_id === entityId && edge.from_kind === kind ? edge.to_kind : edge.from_kind;
            const otherId =
              edge.from_id === entityId && edge.from_kind === kind ? edge.to_id : edge.from_id;
            return (
              <li key={idx} className="flex items-center justify-between py-2.5">
                <div className="flex items-center gap-2">
                  {KIND_ICON[otherKind] ?? KIND_ICON.user}
                  <span className="text-body text-slate-700">
                    {otherKind} #{otherId}
                  </span>
                  {edge.relation_type && <Badge variant="info">{edge.relation_type}</Badge>}
                </div>
                <Badge
                  variant={
                    edge.strength >= 60 ? 'success' : edge.strength >= 30 ? 'info' : 'default'
                  }
                >
                  {edge.strength.toFixed(0)}
                </Badge>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

export default RelationshipPanel;
