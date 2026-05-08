import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Sparkles, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';

import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { aiAttributesApi } from '../../lib/api';
import { onAiAttributeValueChanged } from '../../lib/cacheInvalidation';
import { formatDate } from '../../lib/formatters';

/**
 * Round-8 R8-DEAD-2/4 — surface AI attribute values on entity detail pages.
 *
 * Lists active definitions for the entity_type and renders each one's
 * current value (or a "generate" CTA when missing). Persisted values
 * include confidence + model_name + trace_id from the LLM run.
 */
interface AiAttributeValuesPanelProps {
  entityType: string;
  entityId: number;
}

export function AiAttributeValuesPanel({ entityType, entityId }: AiAttributeValuesPanelProps) {
  const qc = useQueryClient();

  const definitionsQuery = useQuery({
    queryKey: ['ai-attributes', 'definitions', entityType],
    queryFn: () => aiAttributesApi.listDefinitions(entityType, true),
  });

  const valuesQuery = useQuery({
    queryKey: ['ai-attributes', 'values', entityType, entityId],
    queryFn: () => aiAttributesApi.listValues(entityType, entityId),
    enabled: entityId > 0,
  });

  const generateMutation = useMutation({
    mutationFn: (definitionId: number) =>
      aiAttributesApi.generate(definitionId, { entity_id: entityId }),
    onSuccess: () => {
      toast.success('AI değeri yenilendi');
      onAiAttributeValueChanged(qc, entityType, entityId);
    },
    onError: () => toast.error('AI değer üretilemedi'),
  });

  const definitions = definitionsQuery.data?.items ?? [];
  const values = valuesQuery.data?.items ?? [];
  const valueByDefId = new Map(values.map((v) => [v.definition_id, v]));

  const isLoading = definitionsQuery.isLoading || valuesQuery.isLoading;

  if (isLoading) {
    return (
      <Card title="AI öznitelikleri">
        <Skeleton className="h-24" />
      </Card>
    );
  }

  if (definitions.length === 0) {
    return (
      <Card title="AI öznitelikleri" description="Bu varlık tipi için henüz AI tanımı yok">
        <EmptyState
          title="Tanım yok"
          description="Yöneticiden bu varlık tipi için AI öznitelik tanımı eklemesini iste."
          variant="compact"
          icon={<Sparkles className="h-8 w-8 text-slate-400" />}
        />
      </Card>
    );
  }

  return (
    <Card title="AI öznitelikleri" description="LLM ile üretilmiş kalıcı alanlar">
      <ul className="divide-y divide-slate-100">
        {definitions.map((def) => {
          const v = valueByDefId.get(def.id);
          const generating = generateMutation.isPending && generateMutation.variables === def.id;
          return (
            <li key={def.id} className="flex items-start justify-between gap-3 py-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-3 w-3 text-honeywell-red" />
                  <span className="text-body-strong text-slate-800 dark:text-slate-100">
                    {def.label}
                  </span>
                  {v?.confidence != null && (
                    <Badge variant={v.confidence >= 0.6 ? 'success' : 'info'}>
                      {Math.round(v.confidence * 100)}%
                    </Badge>
                  )}
                </div>
                {v ? (
                  <>
                    <p className="mt-1 text-caption text-slate-700 dark:text-slate-300 break-words">
                      {renderValue(v.value)}
                    </p>
                    <p className="mt-1 text-[11px] text-slate-400">
                      {v.model_name ?? 'unknown'} ·{' '}
                      {v.generated_at ? formatDate(v.generated_at) : '—'}
                    </p>
                  </>
                ) : (
                  <p className="mt-1 text-caption text-slate-400">Henüz değer üretilmedi</p>
                )}
              </div>
              <Button
                variant="tertiary"
                size="sm"
                onClick={() => generateMutation.mutate(def.id)}
                disabled={generating}
              >
                <RefreshCw className={`mr-1 h-3 w-3 ${generating ? 'animate-spin' : ''}`} />
                {v ? 'Yenile' : 'Üret'}
              </Button>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

function renderValue(v: unknown): string {
  if (v === null || v === undefined) return '—';
  if (typeof v === 'boolean') return v ? 'Evet' : 'Hayır';
  if (Array.isArray(v)) return v.join(', ');
  return String(v);
}

export default AiAttributeValuesPanel;
