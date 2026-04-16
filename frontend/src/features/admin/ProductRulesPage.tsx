import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Card } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { productRulesApi } from '../../lib/api';

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

  const { data, isLoading } = useQuery<{ items: ProductRule[] }>({
    queryKey: ['productRules'],
    queryFn: () => productRulesApi.list(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => productRulesApi.create(payload),
    onSuccess: () => {
      toast.success('Urun kurali olusturuldu');
      setIsCreateOpen(false);
      setForm(INITIAL_FORM);
      queryClient.invalidateQueries({ queryKey: ['productRules'] });
    },
    onError: () => toast.error('Urun kurali olusturulamadi'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => productRulesApi.remove(id),
    onSuccess: () => {
      toast.success('Urun kurali silindi');
      setDeleteTarget(null);
      queryClient.invalidateQueries({ queryKey: ['productRules'] });
    },
    onError: () => {
      toast.error('Urun kurali silinemedi');
      setDeleteTarget(null);
    },
  });

  const evaluateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => productRulesApi.evaluate(payload),
    onSuccess: (result: EvaluateResult) => {
      setEvaluateResults(result.actions);
      toast.success('Degerlendirme tamamlandi');
    },
    onError: () => toast.error('Degerlendirme basarisiz'),
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
      toast.error('Kosul JSON formati gecersiz');
      return;
    }

    try {
      if (form.action_json.trim()) {
        actionParsed = JSON.parse(form.action_json);
      }
    } catch {
      toast.error('Aksiyon JSON formati gecersiz');
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
      <PageHeader
        title="Urun Kurallari"
        description="Urun fiyatlama ve is kurallarini yonetin"
      >
        <Button onClick={() => setIsCreateOpen(true)}>Yeni Kural</Button>
      </PageHeader>

      {isLoading && <Skeleton variant="card" count={3} />}

      {!isLoading && rules.length === 0 && (
        <EmptyState
          title="Urun kurali bulunamadi"
          description="Yeni bir urun kurali olusturun"
        />
      )}

      {!isLoading && rules.length > 0 && (
        <div className="mb-8 space-y-4">
          {rules.map((rule) => (
            <Card key={rule.id}>
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <h3 className="text-sm font-semibold text-gray-900">{rule.rule_type}</h3>
                    <Badge variant={rule.is_active ? 'success' : 'default'}>
                      {rule.is_active ? 'Aktif' : 'Pasif'}
                    </Badge>
                    <Badge variant="info">Oncelik: {rule.priority}</Badge>
                  </div>

                  <div className="space-y-1 text-xs text-gray-500">
                    <p>
                      <span className="font-medium">Kosul:</span>{' '}
                      <code className="rounded bg-gray-100 px-1 py-0.5">
                        {truncateJson(rule.condition_json)}
                      </code>
                    </p>
                    <p>
                      <span className="font-medium">Aksiyon:</span>{' '}
                      <code className="rounded bg-gray-100 px-1 py-0.5">
                        {truncateJson(rule.action_json)}
                      </code>
                    </p>
                  </div>
                </div>

                <Button size="sm" variant="danger" onClick={() => setDeleteTarget(rule.id)}>
                  Sil
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Evaluate section */}
      <Card title="Kural Test Et" className="mt-8">
        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Yedek Parca ID"
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
            onChange={(e) => setEvaluateForm({ ...evaluateForm, quantity: parseInt(e.target.value, 10) || 0 })}
          />
          <Input
            label="Birim Fiyat"
            type="number"
            value={String(evaluateForm.unit_price)}
            onChange={(e) => setEvaluateForm({ ...evaluateForm, unit_price: parseFloat(e.target.value) || 0 })}
          />
        </div>

        <div className="mt-4">
          <Button onClick={handleEvaluate} loading={evaluateMutation.isPending}>
            Test Et
          </Button>
        </div>

        {evaluateResults !== null && (
          <div className="mt-4">
            <p className="mb-2 text-sm font-medium text-gray-700">Sonuclar:</p>
            {evaluateResults.length === 0 ? (
              <p className="text-sm text-gray-500">Eslesme bulunamadi</p>
            ) : (
              <div className="flex flex-wrap gap-2">
                {evaluateResults.map((action, index) => (
                  <Badge key={index} variant="info">
                    {action}
                  </Badge>
                ))}
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Create modal */}
      <Modal
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        title="Yeni Urun Kurali"
        size="lg"
      >
        <div className="space-y-4">
          <Input
            label="Kural Tipi"
            placeholder="Ornegin: indirim_kurali"
            value={form.rule_type}
            onChange={(e) => setForm({ ...form, rule_type: e.target.value })}
          />
          <div>
            <label htmlFor="condition-json" className="mb-1 block text-sm font-medium text-gray-700">
              Kosul (JSON)
            </label>
            <textarea
              id="condition-json"
              rows={3}
              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light"
              placeholder='{"min_quantity": 10}'
              value={form.condition_json}
              onChange={(e) => setForm({ ...form, condition_json: e.target.value })}
            />
          </div>
          <div>
            <label htmlFor="action-json" className="mb-1 block text-sm font-medium text-gray-700">
              Aksiyon (JSON)
            </label>
            <textarea
              id="action-json"
              rows={3}
              className="block w-full rounded-lg border border-gray-300 px-3 py-2 text-sm transition-colors focus:border-honeywell-red focus:outline-none focus:ring-2 focus:ring-honeywell-light"
              placeholder='{"discount_percent": 5}'
              value={form.action_json}
              onChange={(e) => setForm({ ...form, action_json: e.target.value })}
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Yedek Parca ID"
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
            label="Oncelik"
            type="number"
            value={String(form.priority)}
            onChange={(e) => setForm({ ...form, priority: parseInt(e.target.value, 10) || 1 })}
          />
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
            <Button variant="secondary" onClick={() => setIsCreateOpen(false)}>
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
        title="Urun Kurali Sil"
        message="Bu urun kuralini silmek istediginizden emin misiniz?"
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
