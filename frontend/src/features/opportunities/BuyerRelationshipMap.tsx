import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { stakeholdersApi } from '../../lib/api';
import { onStakeholderChanged } from '../../lib/cacheInvalidation';
import type { Stakeholder, StakeholderAlert } from '../../lib/types';
import { AlertTriangle, CheckCircle, Info, Plus, ShieldAlert, Trash2, User, X } from 'lucide-react';
import { toast } from 'sonner';

const SENIORITY_ORDER = ['executive', 'senior', 'mid_level', 'junior'];
const SENIORITY_LABELS: Record<string, string> = {
  executive: 'Üst Yönetim',
  senior: 'Kidemli',
  mid_level: 'Orta',
  junior: 'Junior',
};
const DEPARTMENT_LABELS: Record<string, string> = {
  tech: 'Teknoloji',
  finance: 'Finans',
  legal: 'Hukuk',
  operations: 'Operasyon',
  sales: 'Satış',
  marketing: 'Pazarlama',
  hr: 'IK',
  other: 'Diğer',
};
const ROLE_LABELS: Record<string, string> = {
  decision_maker: 'Karar Verici',
  influencer: 'Etkileyici',
  champion: 'Sampiyon',
  detractor: 'Muhalif',
  gatekeeper: 'Kapici',
  end_user: 'Son Kullanıcı',
};
const ROLE_COLORS: Record<string, string> = {
  decision_maker: 'bg-purple-100 text-purple-800',
  influencer: 'bg-blue-100 text-blue-800',
  champion: 'bg-green-100 text-green-800',
  detractor: 'bg-red-100 text-red-800',
  gatekeeper: 'bg-yellow-100 text-yellow-800',
  end_user: 'bg-slate-100 text-slate-800',
};

interface BuyerRelationshipMapProps {
  opportunityId: number;
}

export default function BuyerRelationshipMap({ opportunityId }: BuyerRelationshipMapProps) {
  const queryClient = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);

  const { data: stakeholderData } = useQuery({
    queryKey: ['stakeholders', opportunityId],
    queryFn: () => stakeholdersApi.listByOpportunity(opportunityId),
  });

  const { data: alertsData } = useQuery({
    queryKey: ['stakeholder-alerts', opportunityId],
    queryFn: () => stakeholdersApi.getAlerts(opportunityId),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => stakeholdersApi.delete(id),
    onSuccess: () => {
      // R4-CACHE-111 — stakeholder count is a feature input to deal-
      // risk / decision-gap / benchmark cards.
      onStakeholderChanged(queryClient, opportunityId);
      toast.success('Paydas silindi');
    },
  });

  const stakeholders: Stakeholder[] = stakeholderData?.stakeholders ?? [];
  const alerts: StakeholderAlert[] = alertsData?.alerts ?? [];

  const grouped = SENIORITY_ORDER.reduce<Record<string, Stakeholder[]>>((acc, level) => {
    acc[level] = stakeholders.filter((s) => s.seniority === level);
    return acc;
  }, {});
  const ungrouped = stakeholders.filter(
    (s) => !s.seniority || !SENIORITY_ORDER.includes(s.seniority),
  );

  return (
    <div className="space-y-4">
      {/* Alerts */}
      {alerts.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {alerts.map((alert, i) => (
            <div
              key={i}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium ${
                alert.severity === 'warning'
                  ? 'bg-amber-50 text-amber-700 border border-amber-200'
                  : alert.severity === 'risk'
                    ? 'bg-red-50 text-red-700 border border-red-200'
                    : alert.severity === 'positive'
                      ? 'bg-green-50 text-green-700 border border-green-200'
                      : 'bg-blue-50 text-blue-700 border border-blue-200'
              }`}
            >
              {alert.severity === 'warning' && <AlertTriangle className="w-3 h-3" />}
              {alert.severity === 'risk' && <ShieldAlert className="w-3 h-3" />}
              {alert.severity === 'positive' && <CheckCircle className="w-3 h-3" />}
              {alert.severity === 'info' && <Info className="w-3 h-3" />}
              {alert.message}
            </div>
          ))}
        </div>
      )}

      {/* Map Grid */}
      <div className="border rounded-lg overflow-hidden">
        {SENIORITY_ORDER.map((level) => {
          const members = grouped[level];
          if (!members || members.length === 0) return null;
          return (
            <div key={level} className="border-b last:border-b-0">
              <div className="px-4 py-2 bg-slate-50 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                {SENIORITY_LABELS[level] ?? level}
              </div>
              <div className="flex flex-wrap gap-3 p-4">
                {members.map((s) => (
                  <StakeholderCard
                    key={s.id}
                    stakeholder={s}
                    onDelete={() => deleteMutation.mutate(s.id)}
                  />
                ))}
              </div>
            </div>
          );
        })}
        {ungrouped.length > 0 && (
          <div className="border-b last:border-b-0">
            <div className="px-4 py-2 bg-slate-50 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Atanmamis
            </div>
            <div className="flex flex-wrap gap-3 p-4">
              {ungrouped.map((s) => (
                <StakeholderCard
                  key={s.id}
                  stakeholder={s}
                  onDelete={() => deleteMutation.mutate(s.id)}
                />
              ))}
            </div>
          </div>
        )}
        {stakeholders.length === 0 && (
          <div className="p-8 text-center text-slate-400">
            Henüz paydas eklenmemis. Alis komitesini olusturmaya baslayin.
          </div>
        )}
      </div>

      {/* Add Button / Form */}
      {!showAddForm ? (
        <button
          onClick={() => setShowAddForm(true)}
          className="flex items-center gap-1.5 px-3 py-2 text-sm text-blue-600 hover:bg-blue-50 rounded-lg transition"
        >
          <Plus className="w-4 h-4" /> Paydas Ekle
        </button>
      ) : (
        <AddStakeholderForm
          opportunityId={opportunityId}
          onClose={() => setShowAddForm(false)}
          onSuccess={() => {
            onStakeholderChanged(queryClient, opportunityId);
            setShowAddForm(false);
          }}
        />
      )}

      {/* Stats */}
      {stakeholders.length > 0 && (
        <div className="flex gap-4 text-xs text-slate-500">
          <span>{stakeholders.length} kisi</span>
          <span>{alertsData?.departments?.length ?? 0} departman</span>
          <span>{alertsData?.roles?.length ?? 0} rol</span>
        </div>
      )}
    </div>
  );
}

function StakeholderCard({
  stakeholder: s,
  onDelete,
}: {
  stakeholder: Stakeholder;
  onDelete: () => void;
}) {
  return (
    <div className="relative group w-48 border rounded-lg p-3 bg-white hover:shadow-sm transition">
      <button
        onClick={onDelete}
        className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-red-50 text-slate-400 hover:text-red-500 transition"
      >
        <Trash2 className="w-3 h-3" />
      </button>
      <div className="flex items-center gap-2 mb-2">
        <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center">
          <User className="w-4 h-4 text-slate-500" />
        </div>
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">{s.name}</div>
          {s.title && <div className="text-xs text-slate-500 truncate">{s.title}</div>}
        </div>
      </div>
      <div className="flex flex-wrap gap-1">
        {s.department_group && (
          <span className="text-[10px] px-1.5 py-0.5 bg-slate-100 text-slate-600 rounded">
            {DEPARTMENT_LABELS[s.department_group] ?? s.department_group}
          </span>
        )}
        {s.buyer_role && (
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${ROLE_COLORS[s.buyer_role] ?? 'bg-slate-100 text-slate-600'}`}
          >
            {ROLE_LABELS[s.buyer_role] ?? s.buyer_role}
          </span>
        )}
        {/* Auto-detected stakeholders shown with an "AI" pill so the
            rep can tell apart confirmed contacts from algorithmic
            inferences (audit F-12). */}
        {s.is_auto_detected && (
          <span
            title={s.notes ?? undefined}
            className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-purple-50 text-purple-700"
          >
            AI
          </span>
        )}
      </div>
      {/* Direct contact channels — captured at form-time but hidden
          before audit F-12. mailto/tel let the rep act without a
          second tab. */}
      {(s.email || s.phone) && (
        <div className="mt-2 flex flex-col gap-0.5 text-[11px]">
          {s.email && (
            <a
              href={`mailto:${s.email}`}
              className="truncate text-blue-600 hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              {s.email}
            </a>
          )}
          {s.phone && (
            <a
              href={`tel:${s.phone}`}
              className="truncate text-slate-600 hover:underline"
              onClick={(e) => e.stopPropagation()}
            >
              {s.phone}
            </a>
          )}
        </div>
      )}
    </div>
  );
}

function AddStakeholderForm({
  opportunityId,
  onClose,
  onSuccess,
}: {
  opportunityId: number;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [title, setTitle] = useState('');
  const [seniority, setSeniority] = useState('');
  const [department, setDepartment] = useState('');
  const [role, setRole] = useState('');

  const createMutation = useMutation({
    mutationFn: () =>
      stakeholdersApi.create({
        opportunity_id: opportunityId,
        name,
        email: email || undefined,
        title: title || undefined,
        seniority: seniority || undefined,
        department_group: department || undefined,
        buyer_role: role || undefined,
      }),
    onSuccess: () => {
      toast.success('Paydas eklendi');
      onSuccess();
    },
    onError: () => toast.error('Eklenemedi'),
  });

  return (
    <div className="border rounded-lg p-4 bg-slate-50 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">Yeni Paydas</span>
        <button onClick={onClose} className="p-1 hover:bg-gray-200 rounded">
          <X className="w-4 h-4" />
        </button>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <input
          placeholder="Ad Soyad *"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="px-3 py-2 border rounded text-sm"
        />
        <input
          placeholder="Unvan"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className="px-3 py-2 border rounded text-sm"
        />
        <input
          placeholder="E-posta"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="px-3 py-2 border rounded text-sm"
        />
        <select
          value={seniority}
          onChange={(e) => setSeniority(e.target.value)}
          className="px-3 py-2 border rounded text-sm"
        >
          <option value="">Kidemlilik</option>
          {SENIORITY_ORDER.map((s) => (
            <option key={s} value={s}>
              {SENIORITY_LABELS[s]}
            </option>
          ))}
        </select>
        <select
          value={department}
          onChange={(e) => setDepartment(e.target.value)}
          className="px-3 py-2 border rounded text-sm"
        >
          <option value="">Departman</option>
          {Object.entries(DEPARTMENT_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="px-3 py-2 border rounded text-sm"
        >
          <option value="">Alici Rolu</option>
          {Object.entries(ROLE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
      </div>
      <button
        disabled={!name || createMutation.isPending}
        onClick={() => createMutation.mutate()}
        className="px-4 py-2 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
      >
        {createMutation.isPending ? 'Ekleniyor...' : 'Ekle'}
      </button>
    </div>
  );
}
