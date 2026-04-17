import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { Modal } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { approvalsApi } from '../../lib/api';

import type { ApprovalRule } from '../../lib/types';

const ENTITY_TYPE_OPTIONS = [
  { value: 'quote', label: 'Teklif' },
];

const CONDITION_TYPE_OPTIONS = [
  { value: 'discount_pct', label: 'Iskonto Orani (%)' },
  { value: 'grand_total', label: 'Genel Toplam' },
  { value: 'deal_amount', label: 'Anlas ma Tutari' },
];

const OPERATOR_OPTIONS = [
  { value: 'gt', label: '> (Buyuk)' },
  { value: 'gte', label: '>= (Buyuk Esit)' },
  { value: 'lt', label: '< (Kucuk)' },
  { value: 'lte', label: '<= (Kucuk Esit)' },
];

const APPROVER_ROLE_OPTIONS = [
  { value: 'sales_manager', label: 'Satış Yoneticisi' },
];

const OPERATOR_SYMBOL: Record<string, string> = {
  gt: '>',
  gte: '>=',
  lt: '<',
  lte: '<=',
};

const CONDITION_LABEL: Record<string, string> = {
  discount_pct: 'Iskonto %',
  grand_total: 'Genel Toplam',
  deal_amount: 'Anlasma Tutari',
};

interface RuleFormData {
  name: string;
  entity_type: string;
  condition_type: string;
  threshold_operator: string;
  threshold_value: string;
  approver_role: string;
  priority: string;
}

const EMPTY_FORM: RuleFormData = {
  name: '',
  entity_type: 'quote',
  condition_type: 'discount_pct',
  threshold_operator: 'gt',
  threshold_value: '',
  approver_role: 'sales_manager',
  priority: '1',
};

export default function ApprovalRulesPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [editingRule, setEditingRule] = useState<ApprovalRule | null>(null);
  const [form, setForm] = useState<RuleFormData>(EMPTY_FORM);
  const [deleteTarget, setDeleteTarget] = useState<ApprovalRule | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['approval-rules'],
    queryFn: () => approvalsApi.getRules(),
  });

  const createMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      approvalsApi.createRule(payload),
    onSuccess: () => {
      toast.success('Kural oluşturuldu');
      queryClient.invalidateQueries({ queryKey: ['approval-rules'] });
      closeForm();
    },
    onError: () => {
      toast.error('Kural oluşturulamadı');
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: number;
      payload: Record<string, unknown>;
    }) => approvalsApi.updateRule(id, payload),
    onSuccess: () => {
      toast.success('Kural guncellendi');
      queryClient.invalidateQueries({ queryKey: ['approval-rules'] });
      closeForm();
    },
    onError: () => {
      toast.error('Kural guncellenemedi');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => approvalsApi.deleteRule(id),
    onSuccess: () => {
      toast.success('Kural silindi');
      queryClient.invalidateQueries({ queryKey: ['approval-rules'] });
      setDeleteTarget(null);
    },
    onError: () => {
      toast.error('Kural silinemedi');
    },
  });

  const toggleMutation = useMutation({
    mutationFn: ({ id, isActive }: { id: number; isActive: boolean }) =>
      approvalsApi.updateRule(id, { is_active: !isActive }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['approval-rules'] });
    },
    onError: () => {
      toast.error('Durum guncellenemedi');
    },
  });

  function openCreate() {
    setEditingRule(null);
    setForm(EMPTY_FORM);
    setShowForm(true);
  }

  function openEdit(rule: ApprovalRule) {
    setEditingRule(rule);
    setForm({
      name: rule.name,
      entity_type: rule.entity_type,
      condition_type: rule.condition_type,
      threshold_operator: rule.threshold_operator,
      threshold_value: String(rule.threshold_value),
      approver_role: rule.approver_role || 'sales_manager',
      priority: String(rule.priority),
    });
    setShowForm(true);
  }

  function closeForm() {
    setShowForm(false);
    setEditingRule(null);
    setForm(EMPTY_FORM);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      name: form.name,
      entity_type: form.entity_type,
      condition_type: form.condition_type,
      threshold_operator: form.threshold_operator,
      threshold_value: parseFloat(form.threshold_value),
      approver_role: form.approver_role,
      priority: parseInt(form.priority, 10),
    };

    if (editingRule) {
      updateMutation.mutate({ id: editingRule.id, payload });
    } else {
      createMutation.mutate(payload);
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending;

  const columns = [
    {
      key: 'name',
      header: 'Kural Adi',
      render: (row: ApprovalRule) => (
        <span className="font-medium text-gray-900 dark:text-white">
          {row.name}
        </span>
      ),
    },
    {
      key: 'entity_type',
      header: 'Varlık Tipi',
      render: (row: ApprovalRule) => (
        <span className="text-gray-700 dark:text-gray-300">
          {row.entity_type === 'quote' ? 'Teklif' : row.entity_type}
        </span>
      ),
    },
    {
      key: 'condition',
      header: 'Kosul',
      render: (row: ApprovalRule) => (
        <span className="text-gray-700 dark:text-gray-300">
          {CONDITION_LABEL[row.condition_type] || row.condition_type}
        </span>
      ),
    },
    {
      key: 'threshold',
      header: 'Esik Değer',
      render: (row: ApprovalRule) => (
        <span className="font-mono text-sm text-gray-700 dark:text-gray-300">
          {OPERATOR_SYMBOL[row.threshold_operator] || row.threshold_operator}{' '}
          {row.threshold_value}
        </span>
      ),
    },
    {
      key: 'approver_role',
      header: 'Onaylayan Rol',
      render: (row: ApprovalRule) => (
        <span className="text-gray-700 dark:text-gray-300">
          {row.approver_role === 'sales_manager'
            ? 'Satış Yoneticisi'
            : row.approver_role || '-'}
        </span>
      ),
    },
    {
      key: 'priority',
      header: 'Oncelik',
      render: (row: ApprovalRule) => (
        <span className="text-gray-700 dark:text-gray-300">{row.priority}</span>
      ),
    },
    {
      key: 'is_active',
      header: 'Aktif',
      render: (row: ApprovalRule) => (
        <button
          type="button"
          role="switch"
          aria-checked={row.is_active}
          className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors
            ${row.is_active ? 'bg-green-500' : 'bg-gray-300 dark:bg-gray-600'}`}
          onClick={(e) => {
            e.stopPropagation();
            toggleMutation.mutate({ id: row.id, isActive: row.is_active });
          }}
        >
          <span
            className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform
              ${row.is_active ? 'translate-x-5' : 'translate-x-0'}`}
          />
        </button>
      ),
    },
    {
      key: 'row_actions',
      header: '',
      render: (row: ApprovalRule) => (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              openEdit(row);
            }}
          >
            Düzenle
          </Button>
          <Button
            size="sm"
            variant="danger"
            onClick={(e) => {
              e.stopPropagation();
              setDeleteTarget(row);
            }}
          >
            Sil
          </Button>
        </div>
      ),
    },
  ];

  const items: ApprovalRule[] = data?.items ?? [];

  return (
    <div className="space-y-4">
      <PageHeader
        title="Onay Kuralları"
        description="Teklif ve fırsat için otomatik onay kurallarini yonetin"
      >
        <Button onClick={openCreate}>Yeni Kural</Button>
      </PageHeader>

      <Card>
        <DataTable
          columns={columns}
          data={items}
          loading={isLoading}
          emptyMessage="Henüz onay kuralı tanimlanmamis"
        />
      </Card>

      {/* Create / Edit Modal */}
      <Modal
        isOpen={showForm}
        onClose={closeForm}
        title={editingRule ? 'Kural Düzenle' : 'Yeni Onay Kuralı'}
        size="lg"
      >
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            label="Kural Adi"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            required
          />

          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Varlık Tipi"
              options={ENTITY_TYPE_OPTIONS}
              value={form.entity_type}
              onChange={(e) =>
                setForm({ ...form, entity_type: e.target.value })
              }
            />
            <Select
              label="Kosul Tipi"
              options={CONDITION_TYPE_OPTIONS}
              value={form.condition_type}
              onChange={(e) =>
                setForm({ ...form, condition_type: e.target.value })
              }
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Operator"
              options={OPERATOR_OPTIONS}
              value={form.threshold_operator}
              onChange={(e) =>
                setForm({ ...form, threshold_operator: e.target.value })
              }
            />
            <Input
              label="Esik Değer"
              type="number"
              step="any"
              value={form.threshold_value}
              onChange={(e) =>
                setForm({ ...form, threshold_value: e.target.value })
              }
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Select
              label="Onaylayan Rol"
              options={APPROVER_ROLE_OPTIONS}
              value={form.approver_role}
              onChange={(e) =>
                setForm({ ...form, approver_role: e.target.value })
              }
            />
            <Input
              label="Oncelik"
              type="number"
              min="1"
              value={form.priority}
              onChange={(e) =>
                setForm({ ...form, priority: e.target.value })
              }
              required
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={closeForm} type="button">
              İptal
            </Button>
            <Button type="submit" loading={isSaving}>
              {editingRule ? 'Güncelle' : 'Oluştur'}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
        title="Kural Sil"
        message={`"${deleteTarget?.name}" kuralini silmek istediginizden emin misiniz? Bu işlem geri alinamaz.`}
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
