import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { playbookApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import { useT } from '../../hooks/useT';
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

/**
 * A step is a "stub" when the auto-promoter / seeder created the row
 * but never filled in the template/description. The read-only step
 * card would render as an empty rectangle in that case, which made it
 * look like the page itself was broken. We treat any step with no
 * meaningful textual content as a stub so the UI can hint that
 * editing is required to bring it to life.
 */
function isStepStub(step: PlaybookStepDef): boolean {
  const hasTemplate = typeof step.template === 'string' && step.template.trim().length > 0;
  const hasDescription = typeof step.description === 'string' && step.description.trim().length > 0;
  return !hasTemplate && !hasDescription;
}

export default function PlaybookDetailPage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
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
  // When *every* step is a stub the read-only view would render
  // numbered circles next to empty boxes — looks broken even though
  // the data is technically valid. Surface a banner so the user
  // knows to click Düzenle and fill the steps in.
  const hasStubSteps = steps.length > 0 && steps.every(isStepStub);

  // Save handler shared by the header button + form submit so the
  // header-level "Kaydet" can drive the same mutation as before.
  const handleSave = () => {
    updateMutation.mutate({
      ...form,
      trigger_conditions_json: JSON.stringify(editConditions),
      steps_json: JSON.stringify(editSteps),
    });
  };

  return (
    <div className="space-y-6">
      <PageHeader title={playbook.name} description={playbook.description ?? undefined}>
        {/* Geri (Back) is always visible — works whether the page was
            reached from the playbooks list or via deep link, falling
            back to the list when there is no history. */}
        <Button
          variant="secondary"
          onClick={() => (window.history.length > 1 ? navigate(-1) : navigate('/playbooks'))}
        >
          <ArrowLeft className="mr-1 inline h-4 w-4" />
          Geri
        </Button>
        {!isEditing ? (
          <Button onClick={startEditing}>Düzenle</Button>
        ) : (
          <>
            <Button variant="secondary" type="button" onClick={() => setIsEditing(false)}>
              İptal
            </Button>
            <Button type="button" loading={updateMutation.isPending} onClick={handleSave}>
              Kaydet
            </Button>
          </>
        )}
      </PageHeader>

      {hasStubSteps && !isEditing && (
        <Card>
          <div className="flex items-start gap-3 p-4 text-sm">
            <span className="mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
              !
            </span>
            <div>
              <p className="font-medium text-slate-900 dark:text-white">
                Adımların içeriği henüz tanımlanmadı
              </p>
              <p className="mt-1 text-slate-500 dark:text-slate-400">
                Bu playbook otomatik şablondan oluşturuldu; her adım için aksiyon tipi, mesaj ve
                önceliği <em>Düzenle</em> ile doldurun. Bilgileri girip <em>Kaydet</em> dediğinizde
                şablon canlı hale gelir.
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Edit form (general-info card) — Save/Cancel now live in the
          PageHeader, so this card focuses on metadata only. */}
      {isEditing && (
        <Card>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSave();
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
            {/* Hidden submit so Enter inside an input still triggers
                the same Kaydet flow as the header button. */}
            <button type="submit" className="hidden" aria-hidden />
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
            <p className="text-sm text-slate-500">{t('common.no_executions')}</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-slate-200 dark:border-slate-800">
                    <th className="pb-2 font-medium text-slate-500">ID</th>
                    <th className="pb-2 font-medium text-slate-500">Durum</th>
                    <th className="pb-2 font-medium text-slate-500">Mevcut Adım</th>
                    <th className="pb-2 font-medium text-slate-500">Başlangıç</th>
                    <th className="pb-2 font-medium text-slate-500">Sonraki Aksiyon</th>
                    <th className="pb-2 font-medium text-slate-500">Bitiş</th>
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
                      <td className="py-2 text-slate-700 dark:text-slate-300">
                        {exec.current_step}
                      </td>
                      <td className="py-2 text-slate-500">{formatDateTime(exec.started_at)}</td>
                      {/* next_action_at — when the delayed scheduler
                          will fire the next step. Was returned by the
                          backend but never typed/rendered, so reps
                          couldn't see "1 gün sonra" countdowns. */}
                      <td className="py-2 text-slate-500">
                        {exec.next_action_at ? formatDateTime(exec.next_action_at) : '—'}
                      </td>
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
