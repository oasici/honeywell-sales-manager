import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
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
      toast.success('Durum guncellendi');
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
      <div className="space-y-4">
        <PageHeader title="Playbook'lar" description="Satış sureci playbook yönetimi" />
        <Skeleton variant="card" count={3} />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Playbook'lar" description="Satış sureci playbook yönetimi">
        <Button onClick={() => setShowCreate(true)}>Yeni Playbook</Button>
      </PageHeader>

      {playbooks.length === 0 ? (
        <Card>
          <EmptyState
            title="Henüz playbook bulunmuyor"
            description="Yeni bir playbook olusturarak baslayabilirsiniz."
            action={<Button onClick={() => setShowCreate(true)}>Yeni Playbook</Button>}
          />
        </Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {playbooks.map((pb) => (
            <Card key={pb.id}>
              <div
                className="flex flex-col gap-3 p-4 cursor-pointer"
                onClick={() => navigate(`/playbooks/${pb.id}`)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') navigate(`/playbooks/${pb.id}`);
                }}
              >
                <div className="flex items-start justify-between">
                  <h3 className="font-semibold text-gray-900 dark:text-white hover:underline">
                    {pb.name}
                  </h3>
                  <Badge variant={pb.is_active ? 'success' : 'default'}>
                    {pb.is_active ? 'Aktif' : 'Pasif'}
                  </Badge>
                </div>

                {pb.description && (
                  <p className="text-sm text-gray-500 dark:text-gray-400 line-clamp-2">
                    {pb.description}
                  </p>
                )}

                <div className="flex items-center gap-2">
                  {pb.category && (
                    <Badge variant={CATEGORY_COLORS[pb.category] ?? 'default'}>
                      {translatePlaybookCategory(pb.category, t)}
                    </Badge>
                  )}
                  <span className="text-xs text-gray-400">{formatDateTime(pb.created_at)}</span>
                </div>

                <div
                  className="flex items-center gap-2 pt-1 border-t border-gray-100 dark:border-gray-700"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      toggleMutation.mutate({ id: pb.id, isActive: pb.is_active });
                    }}
                  >
                    {pb.is_active ? 'Pasife Al' : 'Aktif Et'}
                  </Button>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteMutation.mutate(pb.id);
                    }}
                  >
                    Sil
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      <Modal isOpen={showCreate} onClose={() => setShowCreate(false)} title="Yeni Playbook Oluştur">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate({
              ...form,
              trigger_conditions_json: JSON.stringify(triggerConditions),
              steps_json: JSON.stringify(formSteps),
            });
          }}
          className="space-y-3"
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
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Kategori
            </label>
            <select
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            >
              <option value="retention">Elde Tutma</option>
              <option value="growth">Buyume</option>
              <option value="pipeline">Pipeline</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Tetikleme Kosullari
            </label>
            <ConditionBuilder conditions={triggerConditions} onChange={setTriggerConditions} />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Adımlar
            </label>
            <StepBuilder steps={formSteps} onChange={setFormSteps} />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setShowCreate(false)} type="button">
              İptal
            </Button>
            <Button type="submit" loading={createMutation.isPending}>
              Oluştur
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
