import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Plus, Trash2, Shield } from 'lucide-react';

import { Card } from '../../components/ui/Card';
import { Button } from '../../components/ui/Button';
import { Modal } from '../../components/ui/Modal';
import { Input } from '../../components/ui/Input';
import { Select } from '../../components/ui/Select';
import { Badge } from '../../components/ui/Badge';
import { DataTable } from '../../components/ui/DataTable';
import { Skeleton } from '../../components/ui/Skeleton';
import { ConfirmDialog } from '../../components/ui/ConfirmDialog';
import { QueryErrorBanner } from '../../components/ui/QueryErrorBanner';
import { teamsApi } from '../../lib/api';
import { onSharingRuleChanged } from '../../lib/cacheInvalidation';
import type { SharingRule } from '../../lib/types';

const ENTITY_TYPE_OPTIONS = [
  { value: 'customer', label: 'Müşteri' },
  { value: 'opportunity', label: 'Fırsat' },
  { value: 'quote', label: 'Teklif' },
];

const ACCESS_LEVEL_OPTIONS = [
  { value: 'read', label: 'Salt Okunur' },
  { value: 'read_write', label: 'Okuma/Yazma' },
];

const OPERATOR_OPTIONS = [
  { value: 'eq', label: 'Esit' },
  { value: 'neq', label: 'Esit Değil' },
  { value: 'gt', label: 'Buyuk' },
  { value: 'gte', label: 'Buyuk Esit' },
  { value: 'lt', label: 'Kucuk' },
  { value: 'lte', label: 'Kucuk Esit' },
  { value: 'contains', label: 'İçerir' },
];

const ENTITY_TYPE_LABELS: Record<string, string> = {
  customer: 'Müşteri',
  opportunity: 'Fırsat',
  quote: 'Teklif',
};

const ACCESS_LEVEL_LABELS: Record<string, string> = {
  read: 'Salt Okunur',
  read_write: 'Okuma/Yazma',
};

interface RuleForm {
  name: string;
  entity_type: string;
  criteria_field: string;
  criteria_operator: string;
  criteria_value: string;
  share_with_role: string;
  share_with_user_id: string;
  access_level: string;
}

const INITIAL_FORM: RuleForm = {
  name: '',
  entity_type: 'customer',
  criteria_field: '',
  criteria_operator: 'eq',
  criteria_value: '',
  share_with_role: '',
  share_with_user_id: '',
  access_level: 'read',
};

function parseCriteria(json: string): Array<{ field: string; operator: string; value: string }> {
  try {
    const parsed = JSON.parse(json);
    if (Array.isArray(parsed)) return parsed;
    if (parsed && typeof parsed === 'object') return [parsed];
    return [];
  } catch {
    return [];
  }
}

export default function SharingRulesSection() {
  const queryClient = useQueryClient();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<SharingRule | null>(null);
  const [form, setForm] = useState<RuleForm>(INITIAL_FORM);

  const { data, isLoading, isError, refetch } = useQuery<{ data: SharingRule[] }>({
    queryKey: ['sharing-rules'],
    queryFn: teamsApi.getSharingRules,
  });

  const rules: SharingRule[] = data?.data ?? (Array.isArray(data) ? (data as SharingRule[]) : []);

  const createMutation = useMutation({
    mutationFn: () => {
      const criteria = {
        field: form.criteria_field,
        operator: form.criteria_operator,
        value: form.criteria_value,
      };
      return teamsApi.createSharingRule({
        name: form.name,
        entity_type: form.entity_type,
        criteria_json: JSON.stringify([criteria]),
        share_with_role: form.share_with_role || null,
        share_with_user_id: form.share_with_user_id ? Number(form.share_with_user_id) : null,
        access_level: form.access_level,
      });
    },
    onSuccess: () => {
      toast.success('Paylasim kuralı oluşturuldu');
      onSharingRuleChanged(queryClient);
      setIsModalOpen(false);
      setForm(INITIAL_FORM);
    },
    onError: () => toast.error('Kural oluşturulamadı'),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => teamsApi.deleteSharingRule(id),
    onSuccess: () => {
      toast.success('Paylasim kuralı silindi');
      onSharingRuleChanged(queryClient);
      setDeleteTarget(null);
    },
    onError: () => toast.error('Kural silinemedi'),
  });

  const updateField = (field: keyof RuleForm, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  if (isError) {
    return <QueryErrorBanner variant="block" onRetry={() => refetch()} />;
  }

  if (isLoading) {
    return <Skeleton variant="card" />;
  }

  const columns = [
    {
      key: 'name',
      header: 'Kural Adi',
      render: (row: SharingRule) => (
        <span className="font-medium text-slate-900 dark:text-white">{row.name}</span>
      ),
    },
    {
      key: 'entity_type',
      header: 'Varlık Tipi',
      render: (row: SharingRule) => (
        <Badge variant="info">{ENTITY_TYPE_LABELS[row.entity_type] || row.entity_type}</Badge>
      ),
    },
    {
      key: 'criteria_json',
      header: 'Kriterler',
      render: (row: SharingRule) => {
        const criteria = parseCriteria(row.criteria_json);
        return (
          <div className="flex flex-wrap gap-1">
            {criteria.map((c, idx) => (
              <Badge key={idx} variant="default" size="sm">
                {c.field} {c.operator} {c.value}
              </Badge>
            ))}
            {criteria.length === 0 && <span className="text-xs text-slate-400">-</span>}
          </div>
        );
      },
    },
    {
      key: 'access_level',
      header: 'Erişim',
      render: (row: SharingRule) => (
        <Badge variant={row.access_level === 'read_write' ? 'warning' : 'default'}>
          {ACCESS_LEVEL_LABELS[row.access_level] || row.access_level}
        </Badge>
      ),
    },
    {
      key: 'actions',
      header: 'İşlemler',
      render: (row: SharingRule) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setDeleteTarget(row);
          }}
          className="rounded-lg p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-500 transition-colors dark:hover:bg-red-900/20"
          title="Sil"
        >
          <Trash2 size={14} />
        </button>
      ),
    },
  ];

  return (
    <>
      <Card
        title="Paylasim Kuralları"
        action={
          <Button size="sm" onClick={() => setIsModalOpen(true)}>
            <Plus size={14} className="mr-1.5" />
            Yeni Kural
          </Button>
        }
      >
        {rules.length === 0 ? (
          <div className="flex flex-col items-center py-8 text-center">
            <Shield size={32} className="mb-2 text-slate-300 dark:text-slate-600" />
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Henüz paylasim kuralı tanimlanmamis
            </p>
          </div>
        ) : (
          <DataTable columns={columns} data={rules} />
        )}
      </Card>

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Yeni Paylasim Kuralı"
        size="lg"
      >
        <div className="space-y-4">
          <Input
            label="Kural Adi"
            value={form.name}
            onChange={(e) => updateField('name', e.target.value)}
            placeholder="örnek: Butun Teklifleri Paylas"
          />
          <Select
            label="Varlık Tipi"
            options={ENTITY_TYPE_OPTIONS}
            value={form.entity_type}
            onChange={(e) => updateField('entity_type', e.target.value)}
          />

          <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
              Kriter
            </p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Input
                label="Alan"
                value={form.criteria_field}
                onChange={(e) => updateField('criteria_field', e.target.value)}
                placeholder="örnek: amount"
              />
              <Select
                label="Operator"
                options={OPERATOR_OPTIONS}
                value={form.criteria_operator}
                onChange={(e) => updateField('criteria_operator', e.target.value)}
              />
              <Input
                label="Değer"
                value={form.criteria_value}
                onChange={(e) => updateField('criteria_value', e.target.value)}
                placeholder="örnek: 10000"
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Paylasilan Rol"
              value={form.share_with_role}
              onChange={(e) => updateField('share_with_role', e.target.value)}
              placeholder="örnek: sales_rep"
            />
            <Input
              label="Paylasilan Kullanıcı ID"
              type="number"
              value={form.share_with_user_id}
              onChange={(e) => updateField('share_with_user_id', e.target.value)}
              placeholder="Opsiyonel"
            />
          </div>

          <Select
            label="Erişim Seviyesi"
            options={ACCESS_LEVEL_OPTIONS}
            value={form.access_level}
            onChange={(e) => updateField('access_level', e.target.value)}
          />

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setIsModalOpen(false)}>
              İptal
            </Button>
            <Button
              onClick={() => createMutation.mutate()}
              loading={createMutation.isPending}
              disabled={!form.name || !form.criteria_field}
            >
              Oluştur
            </Button>
          </div>
        </div>
      </Modal>

      <ConfirmDialog
        isOpen={!!deleteTarget}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteMutation.mutate(deleteTarget.id);
          }
        }}
        title="Paylasim Kuralini Sil"
        message={`"${deleteTarget?.name}" kuralı silinecek. Devam etmek istiyor musunuz?`}
        confirmLabel="Sil"
        confirmVariant="danger"
        isLoading={deleteMutation.isPending}
      />
    </>
  );
}
