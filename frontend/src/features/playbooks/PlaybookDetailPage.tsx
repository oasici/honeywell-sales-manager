import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { playbookApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import { ConditionBuilder } from './ConditionBuilder';
import { StepBuilder } from './StepBuilder';

import type {
  Playbook,
  PlaybookExecution,
  TriggerCondition,
  PlaybookStepDef,
} from '../../lib/types';

const CATEGORY_OPTIONS = [
  { value: 'retention', label: 'Elde Tutma' },
  { value: 'growth', label: 'Buyume' },
  { value: 'pipeline', label: 'Pipeline' },
];

const STATUS_COLORS: Record<string, 'default' | 'info' | 'warning' | 'success' | 'danger'> = {
  pending: 'default',
  running: 'info',
  completed: 'success',
  cancelled: 'danger',
  failed: 'danger',
};

function parseConditions(raw: string | null): TriggerCondition[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function parseSteps(raw: string | null): PlaybookStepDef[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export default function PlaybookDetailPage() {
  const { id } = useParams<{ id: string }>();
  const playbookId = Number(id);
  const queryClient = useQueryClient();

  const { data: playbook, isLoading } = useQuery<Playbook>({
    queryKey: ['playbooks', playbookId],
    queryFn: () => playbookApi.get(playbookId),
    enabled: !Number.isNaN(playbookId),
  });

  const { data: executionsData } = useQuery({
    queryKey: ['playbook-executions', playbookId],
    queryFn: () => playbookApi.getExecutions({ playbook_id: playbookId }),
    enabled: !Number.isNaN(playbookId),
  });

  const [isEditing, setIsEditing] = useState(false);
  const [form, setForm] = useState({
    name: '',
    description: '',
    category: '',
    is_active: false,
  });
  const [editConditions, setEditConditions] = useState<TriggerCondition[]>([]);
  const [editSteps, setEditSteps] = useState<PlaybookStepDef[]>([]);

  const startEditing = () => {
    if (!playbook) return;
    setForm({
      name: playbook.name,
      description: playbook.description ?? '',
      category: playbook.category ?? 'retention',
      is_active: playbook.is_active,
    });
    setEditConditions(parseConditions(playbook.trigger_conditions_json));
    setEditSteps(parseSteps(playbook.steps_json));
    setIsEditing(true);
  };

  const updateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => playbookApi.update(playbookId, payload),
    onSuccess: () => {
      toast.success('Playbook güncellendi');
      queryClient.invalidateQueries({ queryKey: ['playbooks', playbookId] });
      setIsEditing(false);
    },
    onError: (err: unknown) =>
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Hata oluştu',
      ),
  });

  const cancelExecutionMutation = useMutation({
    mutationFn: (execId: number) => playbookApi.cancelExecution(execId),
    onSuccess: () => {
      toast.success('Yürütme iptal edildi');
      queryClient.invalidateQueries({ queryKey: ['playbook-executions', playbookId] });
    },
    onError: (err: unknown) =>
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Hata oluştu',
      ),
  });

  if (isLoading || !playbook) {
    return (
      <div className="space-y-4">
        <PageHeader title="Playbook Detay" />
        <Skeleton variant="card" count={2} />
      </div>
    );
  }

  const triggerConditions = parseConditions(playbook.trigger_conditions_json);
  const steps = parseSteps(playbook.steps_json);
  const executions: PlaybookExecution[] = executionsData?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader title={playbook.name} description={playbook.description ?? undefined}>
        {!isEditing && <Button onClick={startEditing}>Düzenle</Button>}
      </PageHeader>

      {/* Edit form */}
      {isEditing && (
        <Card>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              updateMutation.mutate({
                ...form,
                trigger_conditions_json: JSON.stringify(editConditions),
                steps_json: JSON.stringify(editSteps),
              });
            }}
            className="space-y-3 p-4"
          >
            <Input
              label="Ad"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              required
            />
            <Input
              label="Açıklama"
              value={form.description}
              onChange={(e) => setForm({ ...form, description: e.target.value })}
            />
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
                Kategori
              </label>
              <select
                className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white"
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
              >
                {CATEGORY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="is_active"
                checked={form.is_active}
                onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                className="h-4 w-4 rounded border-slate-200"
              />
              <label htmlFor="is_active" className="text-sm text-slate-700 dark:text-slate-300">
                Aktif
              </label>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="secondary" type="button" onClick={() => setIsEditing(false)}>
                İptal
              </Button>
              <Button type="submit" loading={updateMutation.isPending}>
                Kaydet
              </Button>
            </div>
          </form>
        </Card>
      )}

      {/* Trigger conditions */}
      <Card>
        <div className="p-4">
          <h2 className="mb-3 text-lg font-semibold text-slate-900 dark:text-white">
            Tetikleme Kosullari
          </h2>
          {isEditing ? (
            <ConditionBuilder conditions={editConditions} onChange={setEditConditions} />
          ) : (
            <ConditionBuilder conditions={triggerConditions} onChange={() => {}} readOnly />
          )}
        </div>
      </Card>

      {/* Steps stepper */}
      <Card>
        <div className="p-4">
          <h2 className="mb-3 text-lg font-semibold text-slate-900 dark:text-white">Adımlar</h2>
          {isEditing ? (
            <StepBuilder steps={editSteps} onChange={setEditSteps} />
          ) : (
            <StepBuilder steps={steps} onChange={() => {}} readOnly />
          )}
        </div>
      </Card>

      {/* Executions */}
      <Card>
        <div className="p-4">
          <h2 className="mb-3 text-lg font-semibold text-slate-900 dark:text-white">Yurutmeler</h2>
          {executions.length === 0 ? (
            <p className="text-sm text-slate-500">Henüz yürütme bulunmuyor.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800">
                    <th className="pb-2 font-medium text-slate-500">ID</th>
                    <th className="pb-2 font-medium text-slate-500">Durum</th>
                    <th className="pb-2 font-medium text-slate-500">Mevcut Adım</th>
                    <th className="pb-2 font-medium text-slate-500">Baslangic</th>
                    <th className="pb-2 font-medium text-slate-500">Bitis</th>
                    <th className="pb-2 font-medium text-slate-500">İşlem</th>
                  </tr>
                </thead>
                <tbody>
                  {executions.map((exec) => (
                    <tr
                      key={exec.id}
                      className="border-b border-slate-100 dark:border-slate-800 last:border-b-0"
                    >
                      <td className="py-2 text-slate-900 dark:text-white">{exec.id}</td>
                      <td className="py-2">
                        <Badge variant={STATUS_COLORS[exec.status] ?? 'default'}>
                          {exec.status}
                        </Badge>
                      </td>
                      <td className="py-2 text-slate-700 dark:text-slate-300">{exec.current_step}</td>
                      <td className="py-2 text-slate-500">{formatDateTime(exec.started_at)}</td>
                      <td className="py-2 text-slate-500">
                        {exec.completed_at ? formatDateTime(exec.completed_at) : '-'}
                      </td>
                      <td className="py-2">
                        {exec.status === 'running' || exec.status === 'pending' ? (
                          <Button
                            variant="danger"
                            size="sm"
                            onClick={() => cancelExecutionMutation.mutate(exec.id)}
                          >
                            İptal Et
                          </Button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
