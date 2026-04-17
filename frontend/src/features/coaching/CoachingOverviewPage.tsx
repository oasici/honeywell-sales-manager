import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Input } from '../../components/ui/Input';
import { Modal } from '../../components/ui/Modal';
import { Badge } from '../../components/ui/Badge';
import { Skeleton } from '../../components/ui/Skeleton';
import { EmptyState } from '../../components/ui/EmptyState';
import { coachingApi } from '../../lib/api';
import { formatDateTime, formatPercent } from '../../lib/formatters';

import type { CoachingOverview, CoachingPlan } from '../../lib/types';

const RISK_COLORS: Record<string, string> = {
  healthy: 'text-green-600 bg-green-50 dark:bg-green-900/20 dark:text-green-400',
  needs_improvement: 'text-amber-600 bg-amber-50 dark:bg-amber-900/20 dark:text-amber-400',
  at_risk: 'text-red-600 bg-red-50 dark:bg-red-900/20 dark:text-red-400',
};

const RISK_LABELS: Record<string, string> = {
  healthy: 'Saglikli',
  needs_improvement: 'Gelistirilmeli',
  at_risk: 'Risk Altinda',
};

const PLAN_STATUS_LABELS: Record<string, string> = {
  active: 'Aktif',
  completed: 'Tamamlandi',
  cancelled: 'İptal Edildi',
  draft: 'Taslak',
};

function ProgressBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.min((value / max) * 100, 100);
  return (
    <div className="h-2 w-full rounded-full bg-gray-200 dark:bg-gray-700">
      <div
        className="h-2 rounded-full bg-blue-500 transition-all duration-300"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

interface GoalRow {
  goal: string;
  target: string;
}

const INITIAL_PLAN_FORM = {
  user_id: '',
  weeks: 4,
  start_date: '',
};

export default function CoachingOverviewPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showCreatePlan, setShowCreatePlan] = useState(false);
  const [planForm, setPlanForm] = useState(INITIAL_PLAN_FORM);
  const [goalRows, setGoalRows] = useState<GoalRow[]>([{ goal: '', target: '' }]);

  const [now] = useState(() => {
    // Lazy initializer runs once; ESLint purity rule is satisfied
    // because useState's initializer is explicitly allowed.
    return globalThis.Date.now();
  });

  const { data: overview, isLoading: isOverviewLoading } = useQuery<CoachingOverview>({
    queryKey: ['coaching', 'overview'],
    queryFn: () => coachingApi.getOverview(),
  });

  const { data: plansData, isLoading: isPlansLoading } = useQuery<{
    items: CoachingPlan[];
    total: number;
  }>({
    queryKey: ['coaching', 'plans'],
    queryFn: () => coachingApi.listPlans(),
  });

  const createPlanMutation = useMutation({
    mutationFn: (payload: {
      user_id: number;
      goals_json: string;
      weeks: number;
      start_date: string;
    }) => coachingApi.createPlan(payload),
    onSuccess: () => {
      toast.success('Koçluk plani oluşturuldu');
      queryClient.invalidateQueries({ queryKey: ['coaching', 'plans'] });
      setShowCreatePlan(false);
      setPlanForm(INITIAL_PLAN_FORM);
      setGoalRows([{ goal: '', target: '' }]);
    },
    onError: (err: unknown) =>
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          'Plan olusturulurken hata oluştu',
      ),
  });

  function handleAddGoalRow() {
    setGoalRows([...goalRows, { goal: '', target: '' }]);
  }

  function handleGoalRowChange(index: number, field: keyof GoalRow, value: string) {
    const updated = goalRows.map((row, i) => (i === index ? { ...row, [field]: value } : row));
    setGoalRows(updated);
  }

  function handleRemoveGoalRow(index: number) {
    if (goalRows.length <= 1) return;
    setGoalRows(goalRows.filter((_, i) => i !== index));
  }

  function handleCreatePlan(e: React.FormEvent) {
    e.preventDefault();
    const userId = Number(planForm.user_id);
    if (!userId) {
      toast.error('Geçerli bir temsilci seçin');
      return;
    }
    const validGoals = goalRows.filter((r) => r.goal.trim() !== '');
    if (validGoals.length === 0) {
      toast.error('En az bir hedef ekleyin');
      return;
    }
    const goalsJson = JSON.stringify(validGoals.map((r) => ({ goal: r.goal, target: r.target })));
    createPlanMutation.mutate({
      user_id: userId,
      goals_json: goalsJson,
      weeks: planForm.weeks,
      start_date: planForm.start_date || new Date().toISOString().slice(0, 10),
    });
  }

  if (isOverviewLoading) return <Skeleton variant="card" count={3} />;

  const summary = overview?.summary;
  const reps = overview?.reps ?? [];
  const plans = plansData?.items ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Koçluk Paneli"
        description="Satış temsilcilerinin performans takibi ve koçluk planlari"
      >
        <Button onClick={() => setShowCreatePlan(true)}>Yeni Koçluk Plani</Button>
      </PageHeader>

      {/* KPI Strip */}
      {summary && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm text-gray-500 dark:text-gray-400">Toplam Temsilci</p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">
                {summary.total_reps}
              </p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm text-gray-500 dark:text-gray-400">Ortalama Skor</p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">
                {formatPercent(summary.avg_score)}
              </p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm text-gray-500 dark:text-gray-400">Düşük Performans</p>
              <p className="text-3xl font-bold text-red-600 dark:text-red-400">
                {summary.low_performers}
              </p>
            </div>
          </Card>
        </div>
      )}

      {/* Rep Cards */}
      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-900 dark:text-white">Temsilciler</h2>
        {reps.length === 0 ? (
          <EmptyState title="Henüz temsilci verisi bulunmuyor" />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {reps.map((rep) => (
              <div
                key={rep.user_id}
                className="cursor-pointer transition-shadow hover:shadow-lg"
                onClick={() => navigate(`/coaching/rep/${rep.user_id}`)}
              >
                <Card>
                  <div className="p-4 space-y-3">
                    {/* Header */}
                    <div className="flex items-center justify-between">
                      <p className="font-medium text-gray-900 dark:text-white">{rep.user_name}</p>
                      <span
                        className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${RISK_COLORS[rep.risk_level] || RISK_COLORS.healthy}`}
                      >
                        {RISK_LABELS[rep.risk_level] || rep.risk_level}
                      </span>
                    </div>

                    {/* Score */}
                    <div className="flex items-center gap-2">
                      <span className="text-2xl font-bold text-gray-900 dark:text-white">
                        {rep.score}
                      </span>
                      <span className="text-sm text-gray-500 dark:text-gray-400">/ 100</span>
                    </div>

                    {/* Indicators */}
                    {rep.indicators.length > 0 && (
                      <div className="space-y-2">
                        {rep.indicators.map((indicator) => (
                          <div key={indicator.name}>
                            <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
                              <span>{indicator.label}</span>
                              <span>{indicator.score}</span>
                            </div>
                            <ProgressBar value={indicator.score} />
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Recommendations */}
                    {rep.recommendations.length > 0 && (
                      <div className="border-t border-gray-100 pt-2 dark:border-gray-700">
                        <p className="mb-1 text-xs font-medium text-gray-500 dark:text-gray-400">
                          Öneriler
                        </p>
                        <ul className="space-y-1">
                          {rep.recommendations.slice(0, 2).map((rec, idx) => (
                            <li key={idx} className="text-xs text-gray-600 dark:text-gray-400">
                              - {rec}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </Card>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Plans List */}
      <div>
        <h2 className="mb-3 text-lg font-semibold text-gray-900 dark:text-white">
          Koçluk Planlari
        </h2>
        {isPlansLoading ? (
          <Skeleton variant="card" count={2} />
        ) : plans.length === 0 ? (
          <EmptyState title="Henüz koçluk plani olusturulmamis" />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {plans.map((plan) => {
              const currentWeek =
                plan.status === 'active' && plan.start_date
                  ? Math.max(
                      1,
                      Math.min(
                        plan.weeks,
                        Math.ceil(
                          (now - new Date(plan.start_date).getTime()) / (7 * 24 * 60 * 60 * 1000),
                        ),
                      ),
                    )
                  : null;

              let parsedGoals: Array<{ goal: string; target: string }> = [];
              try {
                const raw: unknown = JSON.parse(plan.goals_json);
                if (Array.isArray(raw)) {
                  parsedGoals = raw as typeof parsedGoals;
                }
              } catch {
                parsedGoals = [];
              }

              const statusVariant =
                plan.status === 'active'
                  ? 'success'
                  : plan.status === 'completed'
                    ? 'info'
                    : 'default';

              return (
                <Card key={plan.id}>
                  <div className="p-4 space-y-3">
                    {/* Header */}
                    <div className="flex items-center justify-between">
                      <p className="font-medium text-gray-900 dark:text-white">{plan.user_name}</p>
                      <Badge variant={statusVariant}>
                        {PLAN_STATUS_LABELS[plan.status] || plan.status}
                      </Badge>
                    </div>

                    {/* Meta */}
                    <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                      <span>{plan.weeks} hafta</span>
                      {plan.start_date && <span>Baslangic: {formatDateTime(plan.start_date)}</span>}
                    </div>

                    {/* Progress */}
                    {currentWeek !== null && (
                      <div>
                        <div className="flex items-center justify-between text-xs text-gray-600 dark:text-gray-400 mb-1">
                          <span>İlerleme</span>
                          <span>
                            {currentWeek} / {plan.weeks} hafta (
                            {Math.round((currentWeek / plan.weeks) * 100)}%)
                          </span>
                        </div>
                        <ProgressBar value={currentWeek} max={plan.weeks} />
                      </div>
                    )}

                    {/* Goals */}
                    {parsedGoals.length > 0 && (
                      <div className="border-t border-gray-100 dark:border-gray-700 pt-2">
                        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-gray-400">
                          Hedefler
                        </p>
                        <ul className="space-y-1">
                          {parsedGoals.slice(0, 3).map((g, idx) => (
                            <li
                              key={idx}
                              className="flex items-start justify-between gap-2 text-xs"
                            >
                              <span className="text-gray-600 dark:text-gray-400 flex-1">
                                {g.goal}
                              </span>
                              {g.target && (
                                <span className="shrink-0 rounded-full bg-blue-50 dark:bg-blue-900/20 px-2 py-0.5 text-xs font-medium text-blue-700 dark:text-blue-300">
                                  {g.target}
                                </span>
                              )}
                            </li>
                          ))}
                          {parsedGoals.length > 3 && (
                            <li className="text-xs text-gray-400">
                              +{parsedGoals.length - 3} hedef daha
                            </li>
                          )}
                        </ul>
                      </div>
                    )}

                    <p className="text-xs text-gray-400 dark:text-gray-500">
                      Olusturulma: {formatDateTime(plan.created_at)}
                    </p>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>

      {/* Create Plan Modal */}
      <Modal
        isOpen={showCreatePlan}
        onClose={() => setShowCreatePlan(false)}
        title="Yeni Koçluk Plani Oluştur"
      >
        <form onSubmit={handleCreatePlan} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Temsilci
            </label>
            <select
              className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm dark:border-gray-700 dark:bg-gray-800 dark:text-white"
              value={planForm.user_id}
              onChange={(e) => setPlanForm({ ...planForm, user_id: e.target.value })}
              required
            >
              <option value="">Temsilci seçin</option>
              {reps.map((rep) => (
                <option key={rep.user_id} value={rep.user_id}>
                  {rep.user_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Hedefler
            </label>
            <div className="space-y-2">
              {goalRows.map((row, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <Input
                    placeholder="Hedef aciklamasi"
                    value={row.goal}
                    onChange={(e) => handleGoalRowChange(idx, 'goal', e.target.value)}
                  />
                  <Input
                    placeholder="Hedef degeri"
                    value={row.target}
                    onChange={(e) => handleGoalRowChange(idx, 'target', e.target.value)}
                    className="w-32"
                  />
                  {goalRows.length > 1 && (
                    <button
                      type="button"
                      onClick={() => handleRemoveGoalRow(idx)}
                      className="shrink-0 text-sm text-red-500 hover:text-red-700"
                    >
                      Sil
                    </button>
                  )}
                </div>
              ))}
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="mt-2"
              onClick={handleAddGoalRow}
            >
              Hedef Ekle
            </Button>
          </div>
          <Input
            label="Süre (Hafta)"
            type="number"
            value={planForm.weeks}
            onChange={(e) => setPlanForm({ ...planForm, weeks: Number(e.target.value) })}
            required
          />
          <Input
            label="Baslangic Tarihi"
            type="date"
            value={planForm.start_date}
            onChange={(e) => setPlanForm({ ...planForm, start_date: e.target.value })}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setShowCreatePlan(false)} type="button">
              İptal
            </Button>
            <Button type="submit" loading={createPlanMutation.isPending}>
              Oluştur
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
