import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Bot, RefreshCw, X } from 'lucide-react';
import { toast } from 'sonner';

import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { EmptyState } from '../../components/ui/EmptyState';
import { Skeleton } from '../../components/ui/Skeleton';
import { nbaApi } from '../../lib/api';
import { formatDate } from '../../lib/formatters';

/**
 * S-G — NBA tray.
 * Embedded in OpportunityDetailPage. Lists current AI-sourced action queue
 * and provides "regenerate" + "dismiss" controls.
 */
interface NbaTrayProps {
  opportunityId: number;
}

export function NbaTray({ opportunityId }: NbaTrayProps) {
  const qc = useQueryClient();
  const [generating, setGenerating] = useState(false);

  const listQuery = useQuery({
    queryKey: ['nba', opportunityId],
    queryFn: () => nbaApi.list(opportunityId, false),
    enabled: opportunityId > 0,
  });

  const generateMutation = useMutation({
    mutationFn: () => nbaApi.generate(opportunityId, 5),
    onMutate: () => setGenerating(true),
    onSuccess: () => {
      toast.success('Yeni öneriler hazırlandı');
      qc.invalidateQueries({ queryKey: ['nba', opportunityId] });
    },
    onError: () => toast.error('Öneri üretilemedi'),
    onSettled: () => setGenerating(false),
  });

  const dismissMutation = useMutation({
    mutationFn: (taskId: number) => nbaApi.dismiss(opportunityId, taskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['nba', opportunityId] });
    },
    // Round-8 R8-CACHE-5 — surface failures so silent dismisses don't pile up.
    onError: () => toast.error('Aksiyon kapatılamadı'),
  });

  const items = listQuery.data?.items ?? [];

  return (
    <Card
      title="Önerilen aksiyonlar"
      description="Sıradaki en iyi adım — AI üretimi"
      action={
        <Button
          variant="tertiary"
          size="sm"
          onClick={() => generateMutation.mutate()}
          disabled={generating}
        >
          <RefreshCw className={`mr-1 h-3 w-3 ${generating ? 'animate-spin' : ''}`} />
          Yenile
        </Button>
      }
    >
      {listQuery.isLoading && (
        <div className="space-y-2">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-12" />
          ))}
        </div>
      )}

      {!listQuery.isLoading && items.length === 0 && (
        <EmptyState
          title="Henüz öneri yok"
          description="Yenile butonuna basarak ilk önerileri üret."
          variant="compact"
          icon={<Bot className="h-8 w-8 text-slate-400" />}
        />
      )}

      {!listQuery.isLoading && items.length > 0 && (
        <ul className="divide-y divide-slate-100">
          {items.map((task) => (
            <li
              key={task.id}
              className="flex items-start justify-between gap-3 py-3"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <Badge
                    variant={
                      task.priority === 'high'
                        ? 'danger'
                        : task.priority === 'low'
                          ? 'default'
                          : 'warning'
                    }
                  >
                    {task.priority}
                  </Badge>
                  <span className="text-body-strong text-slate-800 truncate">
                    {task.title}
                  </span>
                </div>
                {task.description && (
                  <p className="mt-1 text-caption text-slate-500 line-clamp-2">
                    {task.description}
                  </p>
                )}
                {task.due_at && (
                  <p className="mt-1 text-caption text-slate-400">
                    Vade: {formatDate(task.due_at)}
                  </p>
                )}
              </div>
              <button
                aria-label="Kapat"
                className="text-slate-400 hover:text-slate-600"
                onClick={() => dismissMutation.mutate(task.id)}
              >
                <X className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export default NbaTray;
