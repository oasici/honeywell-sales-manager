import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2, X, Workflow, Zap } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import { Select } from '../../components/ui/Select';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { workflowRulesApi } from '../../lib/api';
import { formatDateTime } from '../../lib/formatters';

import type { WorkflowRule } from '../../lib/types';

const ENTITY_TYPE_OPTIONS = [
  { value: 'opportunity', label: 'Fırsat' },
  { value: 'quote', label: 'Teklif' },
  { value: 'email', label: 'E-posta' },
  { value: 'customer', label: 'Müşteri' },
];

const TRIGGER_EVENT_OPTIONS: Record<string, { value: string; label: string }[]> = {
  opportunity: [
    { value: 'stage_changed', label: 'Aşama Değişti' },
    { value: 'created', label: 'Oluşturuldu' },
    { value: 'amount_changed', label: 'Tutar Değişti' },
  ],
  quote: [
    { value: 'approved', label: 'Onaylandı' },
    { value: 'sent', label: 'Gönderildi' },
    { value: 'created', label: 'Oluşturuldu' },
  ],
  email: [
    { value: 'parsed', label: 'Ayrıştırma Tamamlandi' },
    { value: 'received', label: 'Alindi' },
  ],
  customer: [
    { value: 'created', label: 'Oluşturuldu' },
    { value: 'updated', label: 'Güncellendi' },
  ],
};

const ACTION_TYPE_OPTIONS = [
  { value: 'send_notification', label: 'Bildirim Gönder' },
  { value: 'create_task', label: 'Gorev Oluştur' },
  { value: 'emit_signal', label: 'Sinyal Yayinla' },
  { value: 'field_update', label: 'Alan Güncelle' },
];

const OPERATOR_OPTIONS = [
  { value: 'eq', label: 'Esit' },
  { value: 'neq', label: 'Esit Değil' },
  { value: 'contains', label: 'İçerir' },
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
      toast.success('İş kuralı oluşturuldu');
      resetForm();
      queryClient.invalidateQueries({ queryKey: ['workflowRules'] });
    },
    onError: () => toast.error('İş kuralı oluşturulamadı'),
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: number; is_active: boolean }) =>
      workflowRulesApi.update(id, { is_active }),
    onSuccess: () => {
      toast.success('Kural durumu guncellendi');
      queryClient.invalidateQueries({ queryKey: ['workflowRules'] });
    },
    onError: () => toast.error('Güncelleme başarısız'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => workflowRulesApi.remove(id),
    onSuccess: () => {
      toast.success('İş kuralı silindi');
      setDeleteTarget(null);
      queryClient.invalidateQueries({ queryKey: ['workflowRules'] });
    },
    onError: () => {
      toast.error('İş kuralı silinemedi');
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
    // Round-10 R10-FE-13 — guard the indexed access; the spread of the
    // possibly-undefined row collapses to `{}` so the new row still
    // satisfies ConditionRow.
    const current = updated[idx] ?? EMPTY_CONDITION;
    updated[idx] = { ...current, [key]: value };
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
    const current = updated[idx] ?? EMPTY_ACTION;
    updated[idx] = { ...current, [key]: value };
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
      <PageHeader title="İş Kuralları" description="Olay tabanlı otomasyon kuralları">
        <Button variant="secondary" onClick={() => navigate('/admin/workflow-rules/flow/new')}>
          <Workflow size={14} />
          Yeni Görsel Kural
        </Button>
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus size={14} />
          Yeni Kural
        </Button>
      </PageHeader>

      {isLoading && <Skeleton variant="table" />}

      {isError && (
        <div className="rounded-2xl border border-red-100 bg-red-50/40 p-8 text-center dark:border-red-900/40 dark:bg-red-950/20">
          <p className="text-[14px] font-medium text-red-700 dark:text-red-400">
            İş kuralları yüklenemedi
          </p>
          <p className="mt-1 text-[12px] text-red-600 dark:text-red-500">
            Sayfayı yeniden yüklemeyi deneyin
          </p>
        </div>
      )}

      {!isLoading && !isError && items.length === 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white py-2 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <EmptyState
            variant="default"
            icon={<Workflow size={20} />}
            title="Henüz iş kuralı tanımlanmamış"
            description="Olaylara göre otomatik aksiyon tetiklemek için ilk kuralı oluşturun."
            action={
              <Button onClick={() => setIsCreateOpen(true)} variant="secondary">
                <Plus size={14} />
                İlk Kuralı Oluştur
              </Button>
            }
          />
        </div>
      )}

      {!isLoading && !isError && items.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {items.map((rule) => (
            <div
              key={rule.id}
              className="flex flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) transition-colors hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex min-w-0 items-start gap-2.5">
                  <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                    <Zap size={14} />
                  </span>
                  <h3 className="truncate text-[14px] font-semibold text-slate-900 dark:text-white">
                    {rule.name}
                  </h3>
                </div>
                <Badge variant={rule.is_active ? 'success' : 'default'} size="sm" dot>
                  {rule.is_active ? 'Aktif' : 'Pasif'}
                </Badge>
              </div>

              <dl className="mt-4 space-y-2 text-[12px]">
                <div className="flex items-center gap-2">
                  <dt className="text-overline text-slate-400 dark:text-slate-500">Varlık</dt>
                  <dd className="text-[12px] text-slate-700 dark:text-slate-200">
                    {entityLabel(rule.entity_type)}
                  </dd>
                </div>
                <div className="flex items-center gap-2">
                  <dt className="text-overline text-slate-400 dark:text-slate-500">Tetik</dt>
                  <dd className="text-[12px] text-slate-700 dark:text-slate-200">
                    {triggerLabel(rule.entity_type, rule.trigger_event)}
                  </dd>
                </div>
                {rule.created_at && (
                  <p className="text-[11px] tabular-nums text-slate-400 dark:text-slate-500">
                    {formatDateTime(rule.created_at)}
                  </p>
                )}
              </dl>

              {/* Conditions + actions chip strip — audit F-13. The
                  rule's actual logic was previously hidden behind the
                  "Görsel Editor" button; admins couldn't tell at a
                  glance what each rule actually does. Best-effort
                  parse with defensive narrowing. */}
              {(rule.conditions_json || rule.actions_json) && (
                <div className="mt-3 space-y-1.5 border-t border-slate-100 pt-3 text-[11px] dark:border-slate-800">
                  {(() => {
                    let conds: unknown = null;
                    try {
                      conds = rule.conditions_json ? JSON.parse(rule.conditions_json) : null;
                    } catch {
                      conds = null;
                    }
                    if (!conds || !Array.isArray(conds) || conds.length === 0) return null;
                    return (
                      <div className="flex flex-wrap items-center gap-1">
                        <span className="text-overline text-slate-400">Koşul</span>
                        {(conds as Array<Record<string, unknown>>).slice(0, 4).map((c, i) => (
                          <span
                            key={i}
                            className="rounded-md bg-slate-100 px-1.5 py-0.5 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                          >
                            {String(c.field ?? c.label ?? 'kural')}{' '}
                            {String(c.op ?? c.operator ?? '')} {String(c.value ?? '')}
                          </span>
                        ))}
                        {(conds as unknown[]).length > 4 && (
                          <span className="text-slate-400">+{(conds as unknown[]).length - 4}</span>
                        )}
                      </div>
                    );
                  })()}
                  {(() => {
                    let acts: unknown = null;
                    try {
                      acts = rule.actions_json ? JSON.parse(rule.actions_json) : null;
                    } catch {
                      acts = null;
                    }
                    if (!acts || !Array.isArray(acts) || acts.length === 0) return null;
                    return (
                      <div className="flex flex-wrap items-center gap-1">
                        <span className="text-overline text-slate-400">Eylem</span>
                        {(acts as Array<Record<string, unknown>>).slice(0, 4).map((a, i) => (
                          <span
                            key={i}
                            className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                          >
                            {String(a.action ?? a.type ?? a.label ?? 'eylem')}
                          </span>
                        ))}
                        {(acts as unknown[]).length > 4 && (
                          <span className="text-slate-400">+{(acts as unknown[]).length - 4}</span>
                        )}
                      </div>
                    );
                  })()}
                </div>
              )}

              <div className="mt-4 flex flex-wrap gap-1.5 border-t border-slate-100 pt-3 dark:border-slate-800">
                <Button
                  size="sm"
                  variant="tertiary"
                  onClick={() => navigate(`/admin/workflow-rules/flow/${rule.id}`)}
                >
                  Görsel Editor
                </Button>
                <Button
                  size="sm"
                  variant="tertiary"
                  onClick={() => toggleMutation.mutate({ id: rule.id, is_active: !rule.is_active })}
                >
                  {rule.is_active ? 'Devre Dışı' : 'Etkinleştir'}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setDeleteTarget(rule.id)}
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

      {/* Create modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={resetForm}
        title="Yeni İş Kuralı"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={resetForm}>
              İptal
            </Button>
            <Button onClick={handleCreate} loading={createMutation.isPending}>
              Oluştur
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Kural Adı"
            placeholder="Örneğin: Yüksek tutar bildirimi"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <div className="grid gap-3 sm:grid-cols-2">
            <Select
              label="Varlık Tipi"
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
          </div>

          {/* Conditions */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50/40 p-4 dark:border-slate-800 dark:bg-slate-900/30">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-overline text-slate-500 dark:text-slate-400">Koşullar</span>
              <Button size="sm" variant="tertiary" onClick={addCondition}>
                <Plus size={12} />
                Koşul Ekle
              </Button>
            </div>
            {conditions.length === 0 ? (
              <p className="text-[12px] text-slate-500 dark:text-slate-400">
                Koşul yok — kural her zaman çalışır
              </p>
            ) : (
              <div className="space-y-2">
                {conditions.map((cond, idx) => (
                  <div key={idx} className="flex items-end gap-2">
                    <Input
                      label={idx === 0 ? 'Alan' : undefined}
                      placeholder="stage"
                      value={cond.field}
                      onChange={(e) => updateCondition(idx, 'field', e.target.value)}
                    />
                    <Select
                      label={idx === 0 ? 'Operatör' : undefined}
                      options={OPERATOR_OPTIONS}
                      value={cond.operator}
                      onChange={(e) => updateCondition(idx, 'operator', e.target.value)}
                    />
                    <Input
                      label={idx === 0 ? 'Değer' : undefined}
                      placeholder="negotiation"
                      value={cond.value}
                      onChange={(e) => updateCondition(idx, 'value', e.target.value)}
                    />
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => removeCondition(idx)}
                      aria-label="Koşulu kaldır"
                    >
                      <X size={14} className="text-red-500" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="rounded-2xl border border-slate-200 bg-slate-50/40 p-4 dark:border-slate-800 dark:bg-slate-900/30">
            <div className="mb-3 flex items-center justify-between">
              <span className="text-overline text-slate-500 dark:text-slate-400">Aksiyonlar</span>
              <Button size="sm" variant="tertiary" onClick={addAction}>
                <Plus size={12} />
                Aksiyon Ekle
              </Button>
            </div>
            <div className="space-y-3">
              {actions.map((action, idx) => (
                <div
                  key={idx}
                  className="rounded-xl border border-slate-200 bg-white p-3 dark:border-slate-700 dark:bg-slate-900"
                >
                  <div className="flex items-end gap-2">
                    <div className="flex-1">
                      <Select
                        label="Tip"
                        options={ACTION_TYPE_OPTIONS}
                        value={action.type}
                        onChange={(e) => updateAction(idx, 'type', e.target.value)}
                      />
                    </div>
                    {actions.length > 1 && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => removeAction(idx)}
                        aria-label="Aksiyonu kaldır"
                      >
                        <X size={14} className="text-red-500" />
                      </Button>
                    )}
                  </div>
                  <div className="mt-3 space-y-2">
                    <Input
                      label="Başlık"
                      placeholder="Bildirim başlığı"
                      value={action.title}
                      onChange={(e) => updateAction(idx, 'title', e.target.value)}
                    />
                    <Input
                      label="Mesaj"
                      placeholder="Detay mesajı"
                      value={action.message}
                      onChange={(e) => updateAction(idx, 'message', e.target.value)}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <label className="flex cursor-pointer select-none items-center gap-2.5 rounded-[10px] border border-slate-200 bg-slate-50/60 px-3.5 py-2.5 text-[13px] text-slate-700 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-200">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
              className="h-4 w-4 cursor-pointer rounded-[4px] border-slate-300 text-honeywell-red focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800"
            />
            Aktif
          </label>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget !== null && deleteMutation.mutate(deleteTarget)}
        title="İş Kuralı Sil"
        message="Bu is kuralini silmek istediginizden emin misiniz?"
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
