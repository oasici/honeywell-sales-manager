import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import {
  Map,
  Plus,
  ChevronRight,
  ChevronDown,
  Trash2,
  UserPlus,
  Check,
  Code2,
  RefreshCw,
  Building2,
} from 'lucide-react';
import { territoriesApi, usersApi } from '../../lib/api';
import { onTerritoryChanged } from '../../lib/cacheInvalidation';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';
import type { Territory, TerritoryAssignment, User } from '../../lib/types';
import { formatCurrency } from '../../lib/formatters';
import { useT } from '../../hooks/useT';

// ── Schemas ──────────────────────────────────────────

const territorySchema = z.object({
  name: z.string().min(1, 'Bölge adi zorunlu'),
  parent_id: z.number().optional().nullable(),
  region: z.string().optional(),
  description: z.string().optional(),
});

type TerritoryFormData = z.infer<typeof territorySchema>;

const assignSchema = z.object({
  user_id: z.number().min(1, 'Kullanıcı seçin'),
  role: z.string().min(1, 'Rol zorunlu'),
});

type AssignFormData = z.infer<typeof assignSchema>;

const ROLE_OPTIONS = [
  { value: 'owner', label: 'Sahip' },
  { value: 'member', label: 'Üye' },
  { value: 'viewer', label: 'Görüntüleyen' },
];

// ── Rule Row Type ─────────────────────────────────────

interface RuleRow {
  field: string;
  operator: string;
  value: string;
}

// ── Tree Node ─────────────────────────────────────────

interface TreeNodeProps {
  territory: Territory;
  depth: number;
  selectedId: number | null;
  onSelect: (t: Territory) => void;
}

function TreeNode({ territory, depth, selectedId, onSelect }: TreeNodeProps) {
  const [open, setOpen] = useState(true);
  const hasChildren = territory.children && territory.children.length > 0;
  const isSelected = selectedId === territory.id;

  return (
    <div>
      <button
        type="button"
        onClick={() => onSelect(territory)}
        style={{ paddingLeft: `${12 + depth * 16}px` }}
        className={`w-full flex items-center gap-2 py-2 pr-3 rounded-lg text-left text-sm font-medium transition-colors ${
          isSelected
            ? 'bg-honeywell-red/10 text-honeywell-red'
            : 'text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-white/5 hover:text-slate-900 dark:hover:text-white'
        }`}
      >
        {hasChildren ? (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setOpen((o) => !o);
            }}
            className="shrink-0 text-slate-500 hover:text-slate-900 dark:hover:text-white"
          >
            {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </button>
        ) : (
          <span className="w-3.5 shrink-0" />
        )}
        <Building2 size={14} className="shrink-0" />
        <span className="truncate">{territory.name}</span>
        {territory.region && (
          <span className="ml-auto shrink-0 text-[10px] text-slate-500">{territory.region}</span>
        )}
      </button>

      {hasChildren && open && (
        <div>
          {territory.children!.map((child) => (
            <TreeNode
              key={child.id}
              territory={child}
              depth={depth + 1}
              selectedId={selectedId}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Territory Modal ───────────────────────────────────

interface TerritoryModalProps {
  territories: Territory[];
  onClose: () => void;
}

function TerritoryModal({ territories, onClose }: TerritoryModalProps) {
  const queryClient = useQueryClient();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<TerritoryFormData>({ resolver: zodResolver(territorySchema) });

  const createMutation = useMutation({
    mutationFn: (values: TerritoryFormData) =>
      territoriesApi.create({
        name: values.name,
        parent_id: values.parent_id ?? undefined,
        region: values.region,
        description: values.description,
      }),
    onSuccess: () => {
      toast.success('Bölge oluşturuldu');
      onTerritoryChanged(queryClient);
      // Round-12 R12-FE-5 — reset the form before close so re-opening
      // the modal doesn't show stale state from the last submission.
      reset();
      onClose();
    },
    onError: () => toast.error('Bölge oluşturulamadı'),
  });

  return (
    <Modal isOpen onClose={onClose} title="Yeni Bölge" size="sm">
      <form onSubmit={handleSubmit((v) => createMutation.mutate(v))}>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Bölge Adı <span className="text-red-400">*</span>
            </label>
            <input
              {...register('name')}
              className="w-full rounded-lg border border-slate-200 px-3.5 py-2 text-[13px] text-slate-900 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              placeholder="Örneğin: Marmara Bölgesi"
            />
            {errors.name && <p className="mt-1 text-xs text-red-400">{errors.name.message}</p>}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Üst Bölge
            </label>
            <select
              {...register('parent_id', { setValueAs: (v) => (v === '' ? null : Number(v)) })}
              className="w-full rounded-lg border border-slate-200 px-3.5 py-2 text-[13px] text-slate-900 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            >
              <option value="">Yok (Kök Bölge)</option>
              {territories.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Bölge
            </label>
            <input
              {...register('region')}
              className="w-full rounded-lg border border-slate-200 px-3.5 py-2 text-[13px] text-slate-900 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              placeholder="Örneğin: TR-IST"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Açıklama
            </label>
            <textarea
              {...register('description')}
              rows={2}
              className="w-full rounded-lg border border-slate-200 px-3.5 py-2 text-[13px] text-slate-900 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 resize-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            />
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 mt-6">
          <Button type="button" variant="secondary" onClick={onClose}>
            İptal
          </Button>
          <Button type="submit" loading={createMutation.isPending}>
            <Check size={16} />
            {createMutation.isPending ? 'Oluşturuluyor...' : 'Oluştur'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ── Assign Modal ──────────────────────────────────────

interface AssignModalProps {
  territoryId: number;
  users: User[];
  onClose: () => void;
}

function AssignModal({ territoryId, users, onClose }: AssignModalProps) {
  const t = useT();
  const queryClient = useQueryClient();
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AssignFormData>({ resolver: zodResolver(assignSchema) });

  const assignMutation = useMutation({
    mutationFn: (values: AssignFormData) =>
      territoriesApi.addAssignment(territoryId, { user_id: values.user_id, role: values.role }),
    onSuccess: () => {
      toast.success('Kullanıcı atandı');
      onTerritoryChanged(queryClient, territoryId);
      onClose();
    },
    onError: () => toast.error('Atama yapılamadı'),
  });

  return (
    <Modal isOpen onClose={onClose} title="Kullanıcı Ata" size="sm">
      <form onSubmit={handleSubmit((v) => assignMutation.mutate(v))}>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Kullanıcı <span className="text-red-400">*</span>
            </label>
            <select
              {...register('user_id', { setValueAs: (v) => Number(v) })}
              className="w-full rounded-lg border border-slate-200 px-3.5 py-2 text-[13px] text-slate-900 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            >
              <option value="">{t('common.select_user')}</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name} ({u.email})
                </option>
              ))}
            </select>
            {errors.user_id && (
              <p className="mt-1 text-xs text-red-400">{errors.user_id.message}</p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              Rol <span className="text-red-400">*</span>
            </label>
            <select
              {...register('role')}
              className="w-full rounded-lg border border-slate-200 px-3.5 py-2 text-[13px] text-slate-900 transition-[border-color,box-shadow] duration-150 focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 mt-6">
          <Button type="button" variant="secondary" onClick={onClose}>
            İptal
          </Button>
          <Button type="submit" loading={assignMutation.isPending}>
            <Check size={16} />
            {assignMutation.isPending ? 'Ataniyor...' : 'Ata'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ── Rule Editor Modal ─────────────────────────────────

interface RuleEditorModalProps {
  territory: Territory;
  onClose: () => void;
}

function RuleEditorModal({ territory, onClose }: RuleEditorModalProps) {
  const queryClient = useQueryClient();

  const parseRules = (): RuleRow[] => {
    if (!territory.rules_json) return [{ field: '', operator: 'eq', value: '' }];
    try {
      const parsed = JSON.parse(territory.rules_json);
      return Array.isArray(parsed) && parsed.length > 0
        ? parsed
        : [{ field: '', operator: 'eq', value: '' }];
    } catch {
      return [{ field: '', operator: 'eq', value: '' }];
    }
  };

  const [rules, setRules] = useState<RuleRow[]>(parseRules);

  const updateMutation = useMutation({
    mutationFn: () => territoriesApi.update(territory.id, { rules_json: JSON.stringify(rules) }),
    onSuccess: () => {
      toast.success('Kurallar güncellendi');
      onTerritoryChanged(queryClient, territory.id);
      onClose();
    },
    onError: () => toast.error('Kurallar guncellenemedi'),
  });

  const updateRule = (index: number, field: keyof RuleRow, value: string) => {
    setRules((prev) => prev.map((r, i) => (i === index ? { ...r, [field]: value } : r)));
  };

  const addRule = () => setRules((prev) => [...prev, { field: '', operator: 'eq', value: '' }]);
  const removeRule = (index: number) => setRules((prev) => prev.filter((_, i) => i !== index));

  return (
    <Modal isOpen onClose={onClose} title={`Atama Kuralları — ${territory.name}`}>
      <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
        Bu kurallara uyan müşteriler ve fırsatlar otomatik olarak bu bolgeye atanir.
      </p>

      <div className="space-y-3">
        {rules.map((rule, index) => (
          <div key={index} className="flex items-center gap-2">
            <input
              value={rule.field}
              onChange={(e) => updateRule(index, 'field', e.target.value)}
              placeholder="alan (örneğin: city)"
              className="flex-1 rounded border border-slate-200 px-2.5 py-1.5 text-[12px] focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            />
            <select
              value={rule.operator}
              onChange={(e) => updateRule(index, 'operator', e.target.value)}
              className="rounded border border-slate-200 px-2.5 py-1.5 text-[12px] focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            >
              <option value="eq">esit</option>
              <option value="neq">esit değil</option>
              <option value="contains">içerir</option>
              <option value="starts_with">ile baslar</option>
            </select>
            <input
              value={rule.value}
              onChange={(e) => updateRule(index, 'value', e.target.value)}
              placeholder="değer"
              className="flex-1 rounded border border-slate-200 px-2.5 py-1.5 text-[12px] focus:border-honeywell-red focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
            />
            <button
              type="button"
              onClick={() => removeRule(index)}
              className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-500/10 dark:hover:text-red-400 transition-colors"
              disabled={rules.length === 1}
            >
              <Trash2 size={14} />
            </button>
          </div>
        ))}

        <button
          type="button"
          onClick={addRule}
          className="flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-500 dark:text-blue-400 dark:hover:text-blue-300 transition-colors"
        >
          <Plus size={13} />
          Kural Ekle
        </button>
      </div>

      <div className="flex items-center justify-end gap-3 mt-6">
        <Button type="button" variant="secondary" onClick={onClose}>
          İptal
        </Button>
        <Button
          type="button"
          loading={updateMutation.isPending}
          onClick={() => updateMutation.mutate()}
        >
          <Check size={16} />
          {updateMutation.isPending ? 'Kaydediliyor...' : 'Kaydet'}
        </Button>
      </div>
    </Modal>
  );
}

// ── Detail Panel ──────────────────────────────────────

interface DetailPanelProps {
  territory: Territory;
  users: User[];
}

function DetailPanel({ territory, users }: DetailPanelProps) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [assignModalOpen, setAssignModalOpen] = useState(false);
  const [ruleEditorOpen, setRuleEditorOpen] = useState(false);

  const { data: detail } = useQuery<{
    territory: Territory;
    assignments: TerritoryAssignment[];
  }>({
    queryKey: ['territory-detail', territory.id],
    queryFn: () => territoriesApi.get(territory.id),
  });

  const removeAssignmentMutation = useMutation({
    mutationFn: (userId: number) => territoriesApi.removeAssignment(territory.id, userId),
    onSuccess: () => {
      toast.success('Atama kaldırıldı');
      onTerritoryChanged(queryClient, territory.id);
    },
    onError: () => toast.error('Atama kaldirilamadi'),
  });

  const assignments = detail?.assignments ?? [];

  const { data: metrics } = useQuery<{
    territory_id: number;
    customer_count: number;
    opportunity_count: number;
    active_pipeline_total: number;
    currency: string;
  }>({
    queryKey: ['territory-metrics', territory.id],
    queryFn: () => territoriesApi.getMetrics(territory.id),
  });

  const { data: oppsData } = useQuery<{ items: Array<Record<string, unknown>>; total: number }>({
    queryKey: ['territory-opps', territory.id],
    queryFn: () => territoriesApi.listOpportunities(territory.id, { limit: 20, offset: 0 }),
  });

  const opps = useMemo(() => oppsData?.items ?? [], [oppsData]);

  const roleLabel = (role: string) => ROLE_OPTIONS.find((r) => r.value === role)?.label ?? role;

  const roleColor = (role: string) => {
    const colors: Record<string, string> = {
      owner: 'bg-amber-400/15 text-amber-400',
      manager: 'bg-blue-400/15 text-blue-400',
      rep: 'bg-green-400/15 text-green-400',
      viewer: 'bg-gray-400/15 text-slate-400',
    };
    return colors[role] ?? 'bg-gray-400/15 text-slate-400';
  };

  return (
    <div className="space-y-5">
      {/* Header info */}
      <div className="rounded-xl bg-slate-50/60 dark:bg-white/5 border border-slate-200 dark:border-slate-800 p-4 space-y-2">
        <div className="flex items-center gap-2">
          <Map size={16} className="text-honeywell-red shrink-0" />
          <h3 className="text-sm font-semibold text-slate-900 dark:text-white">{territory.name}</h3>
        </div>
        {territory.region && (
          <p className="text-xs text-slate-600 dark:text-slate-400">
            <span className="text-slate-500">Bölge:</span> {territory.region}
          </p>
        )}
        {territory.description && (
          <p className="text-xs text-slate-600 dark:text-slate-400">{territory.description}</p>
        )}
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            Müşteri
          </p>
          <p className="mt-1 text-xl font-bold text-slate-900 dark:text-white">
            {metrics ? metrics.customer_count : '—'}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            Fırsat
          </p>
          <p className="mt-1 text-xl font-bold text-slate-900 dark:text-white">
            {metrics ? metrics.opportunity_count : '—'}
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
          <p className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            Aktif Pipeline
          </p>
          <p className="mt-1 text-xl font-bold text-slate-900 dark:text-white">
            {metrics
              ? formatCurrency(metrics.active_pipeline_total, metrics.currency || 'TRY')
              : '—'}
          </p>
        </div>
      </div>

      {/* Opportunities drill-down */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-400">
            Son Güncellenen Fırsatlar
          </h4>
          <span className="text-xs text-slate-500">{oppsData?.total ?? opps.length}</span>
        </div>
        {opps.length === 0 ? (
          <p className="text-xs text-slate-500 py-3 text-center">Bu bölgede fırsat bulunamadı</p>
        ) : (
          <div className="space-y-2">
            {opps.slice(0, 8).map((o) => (
              <button
                key={String(o.id)}
                type="button"
                onClick={() => navigate(`/opportunities/${String(o.id)}`)}
                className="flex w-full items-start justify-between rounded-lg bg-slate-50/60 dark:bg-white/5 border border-slate-200 dark:border-slate-800 px-3 py-2 text-left hover:bg-slate-100 dark:hover:bg-white/10 transition-colors"
              >
                <div className="min-w-0">
                  <p className="text-xs font-medium text-slate-900 dark:text-white truncate">
                    {String(o.title ?? '')}
                  </p>
                  <p className="text-[10px] text-slate-500">
                    {String(o.stage ?? '-')}{' '}
                    {o.amount != null
                      ? `• ${formatCurrency(Number(o.amount), String(o.currency || 'TRY'))}`
                      : ''}
                  </p>
                </div>
                <ChevronRight size={14} className="shrink-0 text-slate-400 mt-0.5" />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Assignments */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-400">
            Atanan Kullanıcılar
          </h4>
          <Button variant="secondary" size="sm" onClick={() => setAssignModalOpen(true)}>
            <UserPlus size={13} />
            Kullanıcı Ata
          </Button>
        </div>

        {assignments.length === 0 ? (
          <p className="text-xs text-slate-500 py-3 text-center">Bu bolgeye kullanıcı atanmamis</p>
        ) : (
          <div className="space-y-2">
            {assignments.map((a) => (
              <div
                key={a.id}
                className="flex items-center justify-between rounded-lg bg-slate-50/60 dark:bg-white/5 border border-slate-200 dark:border-slate-800 px-3 py-2"
              >
                <div className="min-w-0">
                  <p className="text-xs font-medium text-slate-900 dark:text-white truncate">
                    {a.user?.full_name ?? `Kullanıcı #${a.user_id}`}
                  </p>
                  {a.user?.email && (
                    <p className="text-[10px] text-slate-500 truncate">{a.user.email}</p>
                  )}
                </div>
                <div className="flex items-center gap-2 shrink-0 ml-2">
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${roleColor(a.role)}`}
                  >
                    {roleLabel(a.role)}
                  </span>
                  <button
                    onClick={() => removeAssignmentMutation.mutate(a.user_id)}
                    className="rounded p-1 text-slate-500 hover:bg-red-500/10 hover:text-red-400 transition-colors"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Rule editor button */}
      <button
        onClick={() => setRuleEditorOpen(true)}
        className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-slate-200 dark:border-white/10 py-3 text-xs font-medium text-slate-500 dark:text-slate-400 hover:border-honeywell-red hover:text-honeywell-red dark:hover:border-white/20 dark:hover:text-white transition-colors"
      >
        <Code2 size={14} />
        Atama Kurallarini Düzenle
      </button>

      {assignModalOpen && (
        <AssignModal
          territoryId={territory.id}
          users={users}
          onClose={() => setAssignModalOpen(false)}
        />
      )}

      {ruleEditorOpen && (
        <RuleEditorModal territory={territory} onClose={() => setRuleEditorOpen(false)} />
      )}
    </div>
  );
}

// ── Flatten Tree ──────────────────────────────────────

function flattenTree(territories: Territory[]): Territory[] {
  const result: Territory[] = [];
  const traverse = (items: Territory[]) => {
    for (const t of items) {
      result.push(t);
      if (t.children?.length) traverse(t.children);
    }
  };
  traverse(territories);
  return result;
}

// ── Page ──────────────────────────────────────────────

export default function TerritoryPage() {
  const t = useT();
  const queryClient = useQueryClient();
  const [selectedTerritory, setSelectedTerritory] = useState<Territory | null>(null);
  const [isCreateOpen, setNewModalOpen] = useState(false);

  // R14-FE-1 exempt: page renders its own isError fallback Card below
  // ("Veriler yuklenirken bir hata oluştu") for the primary tree query.
  // Replacing with QueryErrorBanner would duplicate.
  const {
    data: treeData = [],
    isLoading,
    isError,
  } = useQuery<Territory[]>({
    queryKey: ['territories-tree'],
    queryFn: async () => {
      const res = await territoriesApi.getTree();
      return res?.tree ?? res?.items ?? (Array.isArray(res) ? res : []);
    },
  });

  const { data: usersData } = useQuery<{ items: User[] }>({
    queryKey: ['users'],
    queryFn: () => usersApi.getUsers(),
  });

  const autoAssignMutation = useMutation({
    mutationFn: () => territoriesApi.autoAssign(),
    onSuccess: () => {
      toast.success('Otomatik atama tamamlandi');
      onTerritoryChanged(queryClient);
    },
    onError: () => toast.error('Otomatik atama başarısız'),
  });

  const flatTerritories = flattenTree(treeData);
  const users = usersData?.items ?? [];

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Bölge Yönetimi"
          description="Satış bolgelerini ve kullanıcı atamalarini yonetin"
        />
        <Card>
          <div className="p-8 text-center">
            <p className="text-sm text-red-500">
              Veriler yuklenirken bir hata oluştu. Lütfen sayfayi yenileyin.
            </p>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Bölge Yönetimi"
        description="Satış bolgelerini ve kullanıcı atamalarini yonetin"
      >
        <div className="flex items-center gap-2">
          <button
            onClick={() => autoAssignMutation.mutate()}
            disabled={autoAssignMutation.isPending}
            className="flex items-center gap-2 rounded-xl border border-slate-200 dark:border-white/10 bg-white dark:bg-white/5 hover:bg-slate-50 dark:hover:bg-white/10 disabled:opacity-50 px-4 py-2 text-sm font-medium text-slate-600 dark:text-slate-300 transition-colors"
          >
            <RefreshCw size={15} className={autoAssignMutation.isPending ? 'animate-spin' : ''} />
            Otomatik Ata
          </button>
          <Button onClick={() => setNewModalOpen(true)}>
            <Plus size={16} />
            Yeni Bölge
          </Button>
        </div>
      </PageHeader>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Tree */}
        <div className="lg:col-span-1">
          <Card>
            <div className="p-4">
              <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-500">
                Bölge Agaci
              </h3>
              {isLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map((n) => (
                    <div
                      key={n}
                      className="h-8 rounded bg-slate-100 dark:bg-slate-800 animate-pulse"
                    />
                  ))}
                </div>
              ) : treeData.length === 0 ? (
                <div className="py-8 text-center">
                  <Map className="mx-auto mb-2 text-slate-400" size={24} />
                  <p className="text-xs text-slate-400">{t('common.no_territories')}</p>
                </div>
              ) : (
                <div className="space-y-0.5">
                  {treeData.map((t) => (
                    <TreeNode
                      key={t.id}
                      territory={t}
                      depth={0}
                      selectedId={selectedTerritory?.id ?? null}
                      onSelect={setSelectedTerritory}
                    />
                  ))}
                </div>
              )}
            </div>
          </Card>
        </div>

        {/* Detail */}
        <div className="lg:col-span-2">
          {selectedTerritory ? (
            <Card>
              <div className="p-5">
                <DetailPanel territory={selectedTerritory} users={users} />
              </div>
            </Card>
          ) : (
            <div className="flex h-full min-h-[300px] items-center justify-center rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-800">
              <div className="text-center">
                <Map className="mx-auto mb-3 text-slate-300 dark:text-slate-600" size={32} />
                <p className="text-sm font-medium text-slate-500 dark:text-slate-400">
                  Bir bölge seçin
                </p>
                <p className="mt-1 text-xs text-slate-400">
                  Detaylar ve kullanıcı atamalarini goruntuleyin
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {isCreateOpen && (
        <TerritoryModal territories={flatTerritories} onClose={() => setNewModalOpen(false)} />
      )}
    </div>
  );
}
