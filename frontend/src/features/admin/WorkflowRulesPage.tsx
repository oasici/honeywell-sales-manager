import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { workflowRulesApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';

import type { WorkflowRule } from '../../lib/types';

const ENTITY_TYPE_OPTIONS = [
  { value: 'opportunity', label: 'Firsat' },
  { value: 'quote', label: 'Teklif' },
  { value: 'email', label: 'E-posta' },
  { value: 'customer', label: 'Musteri' },
];

const TRIGGER_EVENT_OPTIONS: Record<string, { value: string; label: string }[]> = {
  opportunity: [
    { value: 'stage_changed', label: 'Asama Degisti' },
    { value: 'created', label: 'Olusturuldu' },
    { value: 'amount_changed', label: 'Tutar Degisti' },
  ],
  quote: [
    { value: 'approved', label: 'Onaylandi' },
    { value: 'sent', label: 'Gonderildi' },
    { value: 'created', label: 'Olusturuldu' },
  ],
  email: [
    { value: 'parsed', label: 'Ayristirma Tamamlandi' },
    { value: 'received', label: 'Alindi' },
  ],
  customer: [
    { value: 'created', label: 'Olusturuldu' },
    { value: 'updated', label: 'Guncellendi' },
  ],
};

const ACTION_TYPE_OPTIONS = [
  { value: 'send_notification', label: 'Bildirim Gonder' },
  { value: 'create_task', label: 'Gorev Olustur' },
  { value: 'emit_signal', label: 'Sinyal Yayinla' },
  { value: 'field_update', label: 'Alan Guncelle' },
];

const OPERATOR_OPTIONS = [
  { value: 'eq', label: 'Esit' },
  { value: 'neq', label: 'Esit Degil' },
  { value: 'contains', label: 'Icerir' },
  { value: 'gte', label: 'Buyuk Esit' },
  { value: 'lte', label: 'Kucuk Esit' },
];

interface ConditionRow {
  field: string;
  operator: string;
  value: string;
}

interface ActionRow {
  type: string;
  title: string;
  message: string;
  priority: string;
}

const EMPTY_CONDITION: ConditionRow = { field: '', operator: 'eq', value: '' };
const EMPTY_ACTION: ActionRow = {
  type: 'send_notification',
  title: '',
  message: '',
  priority: 'normal',
};

const INITIAL_FORM = {
  name: '',
  entity_type: 'opportunity',
  trigger_event: 'stage_changed',
  is_active: true,
};

export default function WorkflowRulesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null);
  const [form, setForm] = useState(INITIAL_FORM);
  const [conditions, setConditions] = useState<ConditionRow[]>([]);
  const [actions, setActions] = useState<ActionRow[]>([{ ...EMPTY_ACTION }]);

  const { data, isLoading, isError } = useQuery<{ items: WorkflowRule[]; total: number }>({
    queryKey: ['workflowRules'],
    queryFn: () => workflowRulesApi.list(),
    retry: 1,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => workflowRulesApi.create(payload),
    onSuccess: () => {
      toast.success('Is kurali olusturuldu');
      resetForm();
      queryClient.invalidateQueries({ queryKey: ['workflowRules'] });
    },
    onError: () => toast.error('Is kurali olusturulamadi'),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      workflowRulesApi.update(id, { is_active }),
    onSuccess: () => {
      toast.success('Kural durumu guncellendi');
      queryClient.invalidateQueries({ queryKey: ['workflowRules'] });
    },
    onError: () => toast.error('Guncelleme basarisiz'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => workflowRulesApi.remove(id),
    onSuccess: () => {
      toast.success('Is kurali silindi');
      setDeleteTarget(null);
      queryClient.invalidateQueries({ queryKey: ['workflowRules'] });
    },
    onError: () => {
      toast.error('Is kurali silinemedi');
      setDeleteTarget(null);
    },
  });

  function resetForm() {
    setForm(INITIAL_FORM);
    setConditions([]);
    setActions([{ ...EMPTY_ACTION }]);
    setIsCreateOpen(false);
  }

  function handleCreate() {
    if (!form.name.trim()) {
      toast.error('Kural adi zorunludur');
      return;
    }
    if (actions.length === 0) {
      toast.error('En az bir aksiyon ekleyin');
      return;
    }

    const validConditions = conditions.filter((c) => c.field.trim());
    const validActions = actions.filter((a) => a.type.trim());

    const payload: Record<string, unknown> = {
      name: form.name,
      entity_type: form.entity_type,
      trigger_event: form.trigger_event,
      is_active: form.is_active,
      conditions_json: validConditions.length > 0 ? JSON.stringify(validConditions) : null,
      actions_json: JSON.stringify(validActions),
    };
    createMutation.mutate(payload);
  }

  function addCondition() {
    setConditions([...conditions, { ...EMPTY_CONDITION }]);
  }

  function removeCondition(idx: number) {
    setConditions(conditions.filter((_, i) => i !== idx));
  }

  function updateCondition(idx: number, key: keyof ConditionRow, value: string) {
    const updated = [...conditions];
    updated[idx] = { ...updated[idx], [key]: value };
    setConditions(updated);
  }

  function addAction() {
    setActions([...actions, { ...EMPTY_ACTION }]);
  }

  function removeAction(idx: number) {
    setActions(actions.filter((_, i) => i !== idx));
  }

  function updateAction(idx: number, key: keyof ActionRow, value: string) {
    const updated = [...actions];
    updated[idx] = { ...updated[idx], [key]: value };
    setActions(updated);
  }

  const items = data?.items ?? [];
  const currentTriggerOptions = TRIGGER_EVENT_OPTIONS[form.entity_type] ?? [];

  const entityLabel = (val: string) =>
    ENTITY_TYPE_OPTIONS.find((o) => o.value === val)?.label ?? val;

  const triggerLabel = (entityType: string, triggerEvent: string) => {
    const opts = TRIGGER_EVENT_OPTIONS[entityType] ?? [];
    return opts.find((o) => o.value === triggerEvent)?.label ?? triggerEvent;
  };

  return (
    <div>
      <PageHeader title="Is Kurallari" description="Olay tabanli otomasyon kurallari">
        <Button variant="secondary" onClick={() => navigate('/admin/workflow-rules/flow/new')}>
          Yeni Gorsel Kural
        </Button>
        <Button onClick={() => setIsCreateOpen(true)}>Yeni Kural</Button>
      </PageHeader>

      {isLoading && <Skeleton variant="table" />}

      {isError && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-8 text-center">
          <p className="text-red-600 font-medium">Is kurallari yuklenemedi</p>
          <p className="text-sm text-red-500 mt-1">Sayfa yeniden yuklenmeyi deneyin</p>
        </div>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <div className="rounded-lg border border-dashed border-gray-300 p-12 text-center">
          <p className="text-gray-500">Henuz is kurali tanimlanmamis</p>
          <Button className="mt-4" onClick={() => setIsCreateOpen(true)}>
            Ilk Kurali Olustur
          </Button>
        </div>
      )}

      {!isLoading && !isError && items.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {items.map((rule) => (
            <div key={rule.id} className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
              <div className="flex items-start justify-between">
                <h3 className="font-semibold text-gray-900">{rule.name}</h3>
                <Badge variant={rule.is_active ? 'success' : 'default'}>
                  {rule.is_active ? 'Aktif' : 'Pasif'}
                </Badge>
              </div>

              <div className="mt-3 space-y-1 text-sm text-gray-600">
                <p>
                  <span className="font-medium">Varlik:</span> {entityLabel(rule.entity_type)}
                </p>
                <p>
                  <span className="font-medium">Tetikleyici:</span>{' '}
                  {triggerLabel(rule.entity_type, rule.trigger_event)}
                </p>
                {rule.created_at && (
                  <p className="text-xs text-gray-400">{formatDateTime(rule.created_at)}</p>
                )}
              </div>

              <div className="mt-4 flex gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => navigate(`/admin/workflow-rules/flow/${rule.id}`)}
                >
                  Gorsel Editor
                </Button>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    toggleMutation.mutate({
                      id: rule.id,
                      is_active: !rule.is_active,
                    })
                  }
                >
                  {rule.is_active ? 'Devre Disi Birak' : 'Etkinlestir'}
                </Button>
                <Button size="sm" variant="danger" onClick={() => setDeleteTarget(rule.id)}>
                  Sil
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create modal */}
      <Modal isOpen={isCreateOpen} onClose={resetForm} title="Yeni Is Kurali">
        <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
          <Input
            label="Kural Adi"
            placeholder="Ornegin: Yuksek tutar bildirimi"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />

          <Select
            label="Varlik Tipi"
            options={ENTITY_TYPE_OPTIONS}
            value={form.entity_type}
            onChange={(e) =>
              setForm({
                ...form,
                entity_type: e.target.value,
                trigger_event: TRIGGER_EVENT_OPTIONS[e.target.value]?.[0]?.value ?? '',
              })
            }
          />

          <Select
            label="Tetikleyici Olay"
            options={currentTriggerOptions}
            value={form.trigger_event}
            onChange={(e) => setForm({ ...form, trigger_event: e.target.value })}
          />

          {/* Conditions */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700">Kosullar</label>
              <Button size="sm" variant="secondary" onClick={addCondition}>
                Kosul Ekle
              </Button>
            </div>
            {conditions.length === 0 && (
              <p className="text-xs text-gray-400">Kosul yok - her zaman calisir</p>
            )}
            {conditions.map((cond, idx) => (
              <div key={idx} className="flex gap-2 mb-2 items-end">
                <Input
                  label={idx === 0 ? 'Alan' : undefined}
                  placeholder="stage"
                  value={cond.field}
                  onChange={(e) => updateCondition(idx, 'field', e.target.value)}
                />
                <Select
                  label={idx === 0 ? 'Operator' : undefined}
                  options={OPERATOR_OPTIONS}
                  value={cond.operator}
                  onChange={(e) => updateCondition(idx, 'operator', e.target.value)}
                />
                <Input
                  label={idx === 0 ? 'Deger' : undefined}
                  placeholder="negotiation"
                  value={cond.value}
                  onChange={(e) => updateCondition(idx, 'value', e.target.value)}
                />
                <Button size="sm" variant="danger" onClick={() => removeCondition(idx)}>
                  X
                </Button>
              </div>
            ))}
          </div>

          {/* Actions */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700">Aksiyonlar</label>
              <Button size="sm" variant="secondary" onClick={addAction}>
                Aksiyon Ekle
              </Button>
            </div>
            {actions.map((action, idx) => (
              <div key={idx} className="rounded border border-gray-200 p-3 mb-2 space-y-2">
                <div className="flex gap-2 items-end">
                  <Select
                    label="Tip"
                    options={ACTION_TYPE_OPTIONS}
                    value={action.type}
                    onChange={(e) => updateAction(idx, 'type', e.target.value)}
                  />
                  {actions.length > 1 && (
                    <Button size="sm" variant="danger" onClick={() => removeAction(idx)}>
                      X
                    </Button>
                  )}
                </div>
                <Input
                  label="Baslik"
                  placeholder="Bildirim basligi"
                  value={action.title}
                  onChange={(e) => updateAction(idx, 'title', e.target.value)}
                />
                <Input
                  label="Mesaj"
                  placeholder="Detay mesaji"
                  value={action.message}
                  onChange={(e) => updateAction(idx, 'message', e.target.value)}
                />
              </div>
            ))}
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-700">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              className="rounded border-gray-300"
            />
            Aktif
          </label>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={resetForm}>
              Iptal
            </Button>
            <Button onClick={handleCreate} loading={createMutation.isPending}>
              Olustur
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget !== null && deleteMutation.mutate(deleteTarget)}
        title="Is Kurali Sil"
        message="Bu is kuralini silmek istediginizden emin misiniz?"
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
