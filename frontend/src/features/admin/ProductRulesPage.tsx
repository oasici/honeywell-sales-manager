import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2, Sparkles, FileCode } from 'lucide-react';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { productRulesApi } from '../../lib/api';
import { onProductRuleChanged } from '../../lib/cacheInvalidation';

import type { ProductRule } from '../../lib/types';

interface EvaluateResult {
  actions: string[];
}

const INITIAL_FORM = {
  rule_type: '',
  condition_json: '',
  action_json: '',
  spare_part_id: '',
  category: '',
  priority: 1,
  is_active: true,
};

const INITIAL_EVALUATE = {
  spare_part_id: '',
  category: '',
  quantity: 1,
  unit_price: 0,
};

export default function ProductRulesPage() {
  const queryClient = useQueryClient();

  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<number | null>(null);
  const [form, setForm] = useState(INITIAL_FORM);
  const [evaluateForm, setEvaluateForm] = useState(INITIAL_EVALUATE);
  const [evaluateResults, setEvaluateResults] = useState<string[] | null>(null);

  const { data, isLoading, isError, refetch } = useQuery<{ items: ProductRule[] }>({
    queryKey: ['productRules'],
    queryFn: () => productRulesApi.list(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => productRulesApi.create(payload),
    onSuccess: () => {
      toast.success('Ürün kuralı oluşturuldu');
      setIsCreateOpen(false);
      setForm(INITIAL_FORM);
      onProductRuleChanged(queryClient);
    },
    onError: () => toast.error('Ürün kuralı oluşturulamadı'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => productRulesApi.remove(id),
    onSuccess: () => {
      toast.success('Ürün kuralı silindi');
      setDeleteTarget(null);
      onProductRuleChanged(queryClient);
    },
    onError: () => {
      toast.error('Ürün kuralı silinemedi');
      setDeleteTarget(null);
    },
  });

  const evaluateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => productRulesApi.evaluate(payload),
    onSuccess: (result: EvaluateResult) => {
      setEvaluateResults(result.actions);
      toast.success('Değerlendirme tamamlandı');
    },
    onError: () => toast.error('Değerlendirme başarısız'),
  });

  function handleCreate() {
    if (!form.rule_type.trim()) {
      toast.error('Kural tipi zorunludur');
      return;
    }

    let conditionParsed: Record<string, unknown> = {};
    let actionParsed: Record<string, unknown> = {};

    try {
      if (form.condition_json.trim()) {
        conditionParsed = JSON.parse(form.condition_json);
      }
    } catch {
      toast.error('Koşul JSON formatı geçersiz');
      return;
    }

    try {
      if (form.action_json.trim()) {
        actionParsed = JSON.parse(form.action_json);
      }
    } catch {
      toast.error('Aksiyon JSON formatı geçersiz');
      return;
    }

    const payload: Record<string, unknown> = {
      rule_type: form.rule_type,
      condition_json: conditionParsed,
      action_json: actionParsed,
      priority: form.priority,
      is_active: form.is_active,
    };

    if (form.spare_part_id) {
      payload.spare_part_id = parseInt(form.spare_part_id, 10);
    }
    if (form.category) {
      payload.category = form.category;
    }

    createMutation.mutate(payload);
  }

  function handleEvaluate() {
    const payload: Record<string, unknown> = {
      quantity: evaluateForm.quantity,
      unit_price: evaluateForm.unit_price,
    };
    if (evaluateForm.spare_part_id) {
      payload.spare_part_id = parseInt(evaluateForm.spare_part_id, 10);
    }
    if (evaluateForm.category) {
      payload.category = evaluateForm.category;
    }
    evaluateMutation.mutate(payload);
  }

  function truncateJson(obj: Record<string, unknown>): string {
    const MAX_LENGTH = 60;
    const str = JSON.stringify(obj);
    if (str.length <= MAX_LENGTH) return str;
    return str.slice(0, MAX_LENGTH) + '...';
  }

  const rules = data?.items ?? [];

  return (
    <div>
      <PageHeader title="Ürün Kuralları" description="Ürün fiyatlama ve iş kurallarını yönetin">
        <Button onClick={() => setIsCreateOpen(true)}>
          <Plus size={14} />
          Yeni Kural
        </Button>
      </PageHeader>

      {isError && <QueryErrorBanner variant="block" onRetry={() => refetch()} />}

      {!isError && isLoading && <Skeleton variant="card" count={3} />}

      {!isError && !isLoading && rules.length === 0 && (
        <div className="rounded-2xl border border-slate-200 bg-white py-2 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <EmptyState
            variant="default"
            icon={<FileCode size={20} />}
            title="Ürün kuralı bulunamadı"
            description="Yeni bir ürün kuralı oluşturun"
            action={
              <Button onClick={() => setIsCreateOpen(true)} variant="secondary">
                <Plus size={14} />
                Yeni Kural
              </Button>
            }
          />
        </div>
      )}

      {!isError && !isLoading && rules.length > 0 && (
        <div className="mb-8 space-y-3">
          {rules.map((rule) => (
            <div
              key={rule.id}
              className="rounded-2xl border border-slate-200 bg-white p-5 shadow-(--shadow-xs) transition-colors hover:border-slate-300 dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0 flex-1 space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-[14px] font-semibold text-slate-900 dark:text-white">
                      {rule.rule_type}
                    </h3>
                    <Badge variant={rule.is_active ? 'success' : 'default'} size="sm" dot>
                      {rule.is_active ? 'Aktif' : 'Pasif'}
                    </Badge>
                    <Badge variant="info" size="sm">
                      Öncelik: {rule.priority}
                    </Badge>
                  </div>

                  <div className="space-y-2 text-[12px] text-slate-600 dark:text-slate-400">
                    <div>
                      <span className="text-overline text-slate-400 dark:text-slate-500">
                        Koşul
                      </span>
                      <code className="mt-1 block overflow-x-auto rounded-[8px] bg-slate-50 px-2.5 py-1.5 font-mono text-[12px] text-slate-800 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-200 dark:ring-slate-800">
                        {truncateJson(rule.condition_json)}
                      </code>
                    </div>
                    <div>
                      <span className="text-overline text-slate-400 dark:text-slate-500">
                        Aksiyon
                      </span>
                      <code className="mt-1 block overflow-x-auto rounded-[8px] bg-slate-50 px-2.5 py-1.5 font-mono text-[12px] text-slate-800 ring-1 ring-inset ring-slate-100 dark:bg-slate-800/60 dark:text-slate-200 dark:ring-slate-800">
                        {truncateJson(rule.action_json)}
                      </code>
                    </div>
                  </div>
                </div>

                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setDeleteTarget(rule.id)}
                  aria-label="Sil"
                >
                  <Trash2 size={14} className="text-red-500" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Evaluate section — brand-tinted to suggest "AI / preview" use */}
      <div className="mt-8 rounded-2xl border border-honeywell-red/15 bg-honeywell-red/4 p-5">
        <div className="mb-4 flex items-center gap-2.5">
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-[10px] bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
            <Sparkles size={14} />
          </span>
          <h3 className="text-[14px] font-semibold text-slate-900 dark:text-white">
            Kural Test Et
          </h3>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Yedek Parça ID"
            type="number"
            placeholder="Opsiyonel"
            value={evaluateForm.spare_part_id}
            onChange={(e) => setEvaluateForm({ ...evaluateForm, spare_part_id: e.target.value })}
          />
          <Input
            label="Kategori"
            placeholder="Opsiyonel"
            value={evaluateForm.category}
            onChange={(e) => setEvaluateForm({ ...evaluateForm, category: e.target.value })}
          />
          <Input
            label="Miktar"
            type="number"
            value={String(evaluateForm.quantity)}
            onChange={(e) =>
              setEvaluateForm({ ...evaluateForm, quantity: parseInt(e.target.value, 10) || 0 })
            }
          />
          <Input
            label="Birim Fiyat"
            type="number"
            value={String(evaluateForm.unit_price)}
            onChange={(e) =>
              setEvaluateForm({ ...evaluateForm, unit_price: parseFloat(e.target.value) || 0 })
            }
          />
        </div>

        <div className="mt-4">
          <Button onClick={handleEvaluate} loading={evaluateMutation.isPending}>
            <Sparkles size={14} />
            Test Et
          </Button>
        </div>

        {evaluateResults !== null && (
          <div className="mt-4 border-t border-honeywell-red/15 pt-4">
            <p className="mb-2 text-overline text-slate-500 dark:text-slate-400">Sonuçlar</p>
            {evaluateResults.length === 0 ? (
              <p className="text-[13px] text-slate-500 dark:text-slate-400">Eşleşme bulunamadı</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {evaluateResults.map((action, index) => (
                  <Badge key={index} variant="info" size="md">
                    {action}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Create modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Yeni Ürün Kuralı"
        size="lg"
        footer={
          <>
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>
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
            label="Kural Tipi"
            placeholder="Örneğin: indirim_kurali"
            value={form.rule_type}
            onChange={(e) => setForm({ ...form, rule_type: e.target.value })}
          />
          <div>
            <label
              htmlFor="condition-json"
              className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300"
            >
              Koşul (JSON)
            </label>
            <textarea
              id="condition-json"
              rows={3}
              className="block w-full resize-none rounded-[12px] border border-slate-200 bg-white px-3.5 py-2.5 font-mono text-[12px] text-slate-900 placeholder:text-slate-400 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-transparent dark:text-slate-100 dark:placeholder:text-slate-500"
              placeholder='{"min_quantity": 10}'
              value={form.condition_json}
              onChange={(e) => setForm({ ...form, condition_json: e.target.value })}
            />
          </div>
          <div>
            <label
              htmlFor="action-json"
              className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300"
            >
              Aksiyon (JSON)
            </label>
            <textarea
              id="action-json"
              rows={3}
              className="block w-full resize-none rounded-[12px] border border-slate-200 bg-white px-3.5 py-2.5 font-mono text-[12px] text-slate-900 placeholder:text-slate-400 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-transparent dark:text-slate-100 dark:placeholder:text-slate-500"
              placeholder='{"discount_percent": 5}'
              value={form.action_json}
              onChange={(e) => setForm({ ...form, action_json: e.target.value })}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Yedek Parça ID"
              type="number"
              placeholder="Opsiyonel"
              value={form.spare_part_id}
              onChange={(e) => setForm({ ...form, spare_part_id: e.target.value })}
            />
            <Input
              label="Kategori"
              placeholder="Opsiyonel"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            />
          </div>
          <Input
            label="Öncelik"
            type="number"
            value={String(form.priority)}
            onChange={(e) => setForm({ ...form, priority: parseInt(e.target.value, 10) || 1 })}
          />
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
        title="Ürün Kuralı Sil"
        message="Bu ürün kuralını silmek istediğinizden emin misiniz?"
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
