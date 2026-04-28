import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, BookOpen, Trash2 } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Badge } from '../../components/ui/Badge';
import { Modal } from '../../components/ui/Modal';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { playbookApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';
import { ConditionBuilder } from './ConditionBuilder';
import { StepBuilder } from './StepBuilder';

import type { Playbook, TriggerCondition, PlaybookStepDef } from '../../lib/types';
import { useT } from '../../hooks/useT';
import { translatePlaybookCategory } from '../../lib/labelTranslations';

const CATEGORY_COLORS: Record<string, 'info' | 'success' | 'warning'> = {
  retention: 'info',
  growth: 'success',
  pipeline: 'warning',
};

const EMPTY_FORM = {
  name: '',
  description: '',
  category: 'retention',
};

const EMPTY_CONDITIONS: TriggerCondition[] = [];
const EMPTY_STEPS: PlaybookStepDef[] = [];

export default function PlaybookListPage() {
  const t = useT();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [triggerConditions, setTriggerConditions] = useState<TriggerCondition[]>([
    ...EMPTY_CONDITIONS,
  ]);
  const [formSteps, setFormSteps] = useState<PlaybookStepDef[]>([...EMPTY_STEPS]);

  const { data, isLoading } = useQuery({
    queryKey: ['playbooks'],
    queryFn: () => playbookApi.list(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => playbookApi.create(payload),
    onSuccess: () => {
      toast.success('Playbook oluşturuldu');
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
      setShowCreate(false);
      setForm({ ...EMPTY_FORM });
      setTriggerConditions([...EMPTY_CONDITIONS]);
      setFormSteps([...EMPTY_STEPS]);
    },
    onError: (err: unknown) =>
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Hata oluştu',
      ),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) =>
      playbookApi.update(id, { is_active: !isActive }),
    onSuccess: () => {
      toast.success('Durum güncellendi');
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
    },
    onError: (err: unknown) =>
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Hata oluştu',
      ),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => playbookApi.remove(id),
    onSuccess: () => {
      toast.success('Playbook silindi');
      queryClient.invalidateQueries({ queryKey: ['playbooks'] });
    },
    onError: (err: unknown) =>
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Hata oluştu',
      ),
  });

  const playbooks: Playbook[] = data?.items ?? [];

  if (isLoading) {
    return (
      <div>
        <PageHeader title="Playbook'lar" description="Satış süreci playbook yönetimi" />
        <Skeleton variant="card" count={3} />
      </div>
    );
  }

  return (
    <div>
      <PageHeader title="Playbook'lar" description="Satış süreci playbook yönetimi">
        <Button onClick={() => setShowCreate(true)}>
          <Plus size={14} />
          Yeni Playbook
        </Button>
      </PageHeader>

      {playbooks.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white py-2 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <EmptyState
            variant="default"
            icon={<BookOpen size={20} />}
            title="Henüz playbook bulunmuyor"
            description="Yeni bir playbook oluşturarak başlayabilirsiniz."
            action={
              <Button onClick={() => setShowCreate(true)} variant="secondary">
                <Plus size={14} />
                Yeni Playbook
              </Button>
            }
          />
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {playbooks.map((pb) => (
            <div
              key={pb.id}
              className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) transition-all hover:-translate-y-px hover:border-honeywell-red/30 hover:shadow-(--shadow-sm) dark:border-slate-800 dark:bg-slate-900"
            >
              <div
                className="flex flex-1 flex-col gap-3 cursor-pointer"
                onClick={() => navigate(`/playbooks/${pb.id}`)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') navigate(`/playbooks/${pb.id}`);
                }}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex min-w-0 items-start gap-2.5">
                    <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                      <BookOpen size={14} />
                    </span>
                    <h3 className="truncate text-[14px] font-semibold text-slate-900 dark:text-white">
                      {pb.name}
                    </h3>
                  </div>
                  <Badge variant={pb.is_active ? 'success' : 'default'} size="sm" dot>
                    {pb.is_active ? 'Aktif' : 'Pasif'}
                  </Badge>
                </div>

                {pb.description && (
                  <p className="line-clamp-2 text-[13px] text-slate-500 dark:text-slate-400">
                    {pb.description}
                  </p>
                )}

                <div className="flex items-center gap-2">
                  {pb.category && (
                    <Badge variant={CATEGORY_COLORS[pb.category] ?? 'default'} size="sm">
                      {translatePlaybookCategory(pb.category, t)}
                    </Badge>
                  )}
                  <span className="text-[11px] tabular-nums text-slate-400 dark:text-slate-500">
                    {formatDateTime(pb.created_at)}
                  </span>
                </div>
              </div>

              <div
                className="mt-3 flex items-center gap-1.5 border-t border-slate-100 pt-3 dark:border-slate-800"
                onClick={(e) => e.stopPropagation()}
              >
                <Button
                  variant="tertiary"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleMutation.mutate({ id: pb.id, isActive: pb.is_active });
                  }}
                >
                  {pb.is_active ? 'Pasife Al' : 'Aktif Et'}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteMutation.mutate(pb.id);
                  }}
                  aria-label="Sil"
                  className="ml-auto"
                >
                  <Trash2 size={13} className="text-red-500" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal
        isOpen={showCreate}
        onClose={() => setShowCreate(false)}
        title="Yeni Playbook Oluştur"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setShowCreate(false)} type="button">
              İptal
            </Button>
            <Button type="submit" form="playbook-create-form" loading={createMutation.isPending}>
              Oluştur
            </Button>
          </>
        }
      >
        <form
          id="playbook-create-form"
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate({
              ...form,
              trigger_conditions_json: JSON.stringify(triggerConditions),
              steps_json: JSON.stringify(formSteps),
            });
          }}
          className="space-y-4"
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
          <Select
            label="Kategori"
            options={[
              { value: 'retention', label: 'Elde Tutma' },
              { value: 'growth', label: 'Büyüme' },
              { value: 'pipeline', label: 'Pipeline' },
            ]}
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
          />
          <div>
            <label className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300">
              Tetikleme Koşulları
            </label>
            <ConditionBuilder conditions={triggerConditions} onChange={setTriggerConditions} />
          </div>
          <div>
            <label className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300">
              Adımlar
            </label>
            <StepBuilder steps={formSteps} onChange={setFormSteps} />
          </div>
        </form>
      </Modal>
    </div>
  );
}
