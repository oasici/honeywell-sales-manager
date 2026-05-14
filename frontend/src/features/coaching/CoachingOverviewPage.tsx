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
import { onCoachingPlanChanged } from '../../lib/cacheInvalidation';
import { formatDateTime, formatPercent } from '../../lib/formatters';

import type { CoachingOverview, CoachingPlan } from '../../lib/types';
import { useT } from '../../hooks/useT';
import { translateCoachingPlanStatus, translateCoachingRisk } from '../../lib/labelTranslations';

/**
 * Risk-tier visual tokens.
 *
 * - healthy / low → emerald
 * - needs_improvement / medium → amber
 * - at_risk / high / critical → red
 *
 * V9 UAT #2: backend may emit either the canonical
 * ``healthy/needs_improvement/at_risk`` names OR a generic
 * ``low/medium/high/critical`` flag. We accept both so the badge
 * color always matches severity instead of silently defaulting to
 * "healthy" green when the backend uses an unexpected value.
 */
const RISK_TONE: Record<string, { chip: string; bar: string }> = {
  healthy: {
    chip: 'bg-emerald-50 text-emerald-700 ring-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-400 dark:ring-emerald-900/40',
    bar: 'bg-emerald-500',
  },
  low: {
    chip: 'bg-emerald-50 text-emerald-700 ring-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-400 dark:ring-emerald-900/40',
    bar: 'bg-emerald-500',
  },
  needs_improvement: {
    chip: 'bg-amber-50 text-amber-700 ring-amber-100 dark:bg-amber-950/30 dark:text-amber-400 dark:ring-amber-900/40',
    bar: 'bg-amber-500',
  },
  medium: {
    chip: 'bg-amber-50 text-amber-700 ring-amber-100 dark:bg-amber-950/30 dark:text-amber-400 dark:ring-amber-900/40',
    bar: 'bg-amber-500',
  },
  med: {
    chip: 'bg-amber-50 text-amber-700 ring-amber-100 dark:bg-amber-950/30 dark:text-amber-400 dark:ring-amber-900/40',
    bar: 'bg-amber-500',
  },
  at_risk: {
    chip: 'bg-red-50 text-red-700 ring-red-100 dark:bg-red-950/30 dark:text-red-400 dark:ring-red-900/40',
    bar: 'bg-red-500',
  },
  high: {
    chip: 'bg-red-50 text-red-700 ring-red-100 dark:bg-red-950/30 dark:text-red-400 dark:ring-red-900/40',
    bar: 'bg-red-500',
  },
  critical: {
    chip: 'bg-red-100 text-red-800 ring-red-200 dark:bg-red-950/50 dark:text-red-300 dark:ring-red-900/60',
    bar: 'bg-red-600',
  },
};

/** Fallback uses amber/needs_improvement so unknown values don't
 * silently render as "healthy" green (UAT #2 root cause). */
const RISK_TONE_FALLBACK = RISK_TONE.needs_improvement!;

/**
 * Score-driven progress bar. Color tier comes from the score itself so
 * indicators still semantically grade themselves even when a rep's
 * top-level risk tier is mixed.
 */
function ProgressBar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = Math.min((value / max) * 100, 100);
  const tier = pct >= 70 ? 'healthy' : pct >= 40 ? 'needs_improvement' : 'at_risk';
  // Round-10 R10-FE-13 — RISK_TONE keys cover all three tiers above.
  const bar = RISK_TONE[tier]!.bar;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
      <div
        className={`h-full rounded-full transition-all duration-300 ${bar}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/**
 * Find the strongest and weakest indicator on a rep's score breakdown.
 * Used to surface "Güçlü alan" / "Gelişim alanı" copy on each card so
 * managers can scan the grid without drilling into every rep.
 */
function pickStrongAndWeak(indicators: { name: string; label: string; score: number }[]): {
  strong?: { label: string; score: number };
  weak?: { label: string; score: number };
} {
  if (indicators.length === 0) return {};
  const sorted = [...indicators].sort((a, b) => b.score - a.score);
  // Round-10 R10-FE-13 — guarded by the length === 0 check above so
  // sorted[0] and sorted[length-1] are non-undefined.
  const first = sorted[0]!;
  const last = sorted[sorted.length - 1]!;
  return {
    strong: { label: first.label, score: first.score },
    weak: { label: last.label, score: last.score },
  };
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
  const t = useT();
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
      toast.success(t('coaching.toast_plan_created'));
      onCoachingPlanChanged(queryClient);
      setShowCreatePlan(false);
      setPlanForm(INITIAL_PLAN_FORM);
      setGoalRows([{ goal: '', target: '' }]);
    },
    onError: (err: unknown) =>
      toast.error(
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
          t('coaching.toast_plan_error'),
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
      toast.error(t('coaching.err_select_rep'));
      return;
    }
    const validGoals = goalRows.filter((r) => r.goal.trim() !== '');
    if (validGoals.length === 0) {
      toast.error(t('coaching.err_goals_required'));
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
        title={t('coaching.overview_title')}
        description={t('coaching.overview_description')}
      >
        <Button onClick={() => setShowCreatePlan(true)}>{t('coaching.new_plan')}</Button>
      </PageHeader>

      {/* KPI Strip */}
      {summary && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {t('coaching.kpi_total_reps')}
              </p>
              <p className="text-3xl font-bold text-slate-900 dark:text-white">
                {summary.total_reps}
              </p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {t('coaching.kpi_avg_score')}
              </p>
              <p className="text-3xl font-bold text-slate-900 dark:text-white">
                {formatPercent(summary.avg_score)}
              </p>
            </div>
          </Card>
          <Card>
            <div className="p-4 text-center">
              <p className="text-sm text-slate-500 dark:text-slate-400">
                {t('coaching.kpi_low_perf')}
              </p>
              <p className="text-3xl font-bold text-red-600 dark:text-red-400">
                {summary.low_performers}
              </p>
            </div>
          </Card>
        </div>
      )}

      {/* Rep Cards */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-heading-3 text-slate-900 dark:text-white">
            {t('coaching.section_reps')}
          </h2>
          {reps.length > 0 && (
            <span className="text-[12px] tabular-nums text-slate-500 dark:text-slate-400">
              {reps.length} temsilci
            </span>
          )}
        </div>
        {reps.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-white py-2 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
            <EmptyState
              variant="compact"
              title={t('coaching.reps_empty')}
              description="Aktif temsilci kaydı bulunduğunda her biri için skor ve öneri kartları burada görünecek."
            />
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {reps.map((rep) => {
              const tone = RISK_TONE[rep.risk_level] ?? RISK_TONE_FALLBACK;
              const insight = pickStrongAndWeak(rep.indicators);
              const initials = rep.user_name
                .split(' ')
                .map((n) => n[0])
                .join('')
                .toUpperCase()
                .slice(0, 2);
              return (
                <button
                  key={rep.user_id}
                  type="button"
                  onClick={() => navigate(`/coaching/rep/${rep.user_id}`)}
                  className="group flex flex-col rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-(--shadow-xs) transition-all hover:-translate-y-px hover:border-honeywell-red/30 hover:shadow-(--shadow-sm) focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-800 dark:bg-slate-900"
                >
                  {/* Header — avatar circle + name + risk chip */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 items-start gap-2.5">
                      <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-honeywell-red/10 text-[12px] font-semibold text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
                        {initials}
                      </span>
                      <div className="min-w-0">
                        <p className="truncate text-[14px] font-semibold text-slate-900 dark:text-white">
                          {rep.user_name}
                        </p>
                        <p className="text-[11px] text-slate-500 dark:text-slate-400">Temsilci</p>
                      </div>
                    </div>
                    <span
                      className={[
                        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ring-1 ring-inset',
                        tone.chip,
                      ].join(' ')}
                    >
                      {translateCoachingRisk(rep.risk_level, t)}
                    </span>
                  </div>

                  {/* Score — large tabular-nums anchor */}
                  <div className="mt-4 flex items-baseline gap-1.5">
                    <span className="text-[32px] font-bold leading-none tracking-tight tabular-nums text-slate-900 dark:text-white">
                      {rep.score}
                    </span>
                    <span className="text-[13px] tabular-nums text-slate-400 dark:text-slate-500">
                      / 100
                    </span>
                  </div>

                  {/* Strong / weak insight callouts */}
                  {(insight.strong || insight.weak) && (
                    <div className="mt-4 grid grid-cols-2 gap-2">
                      {insight.strong && (
                        <div className="rounded-xl border border-emerald-100 bg-emerald-50/40 px-2.5 py-2 dark:border-emerald-900/40 dark:bg-emerald-950/20">
                          <p className="text-overline text-emerald-700 dark:text-emerald-400">
                            Güçlü alan
                          </p>
                          <p className="mt-0.5 truncate text-[12px] font-medium text-slate-800 dark:text-slate-100">
                            {insight.strong.label}
                          </p>
                        </div>
                      )}
                      {insight.weak && (
                        <div className="rounded-xl border border-amber-100 bg-amber-50/40 px-2.5 py-2 dark:border-amber-900/40 dark:bg-amber-950/20">
                          <p className="text-overline text-amber-700 dark:text-amber-400">
                            Gelişim alanı
                          </p>
                          <p className="mt-0.5 truncate text-[12px] font-medium text-slate-800 dark:text-slate-100">
                            {insight.weak.label}
                          </p>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Indicator score breakdown */}
                  {rep.indicators.length > 0 && (
                    <div className="mt-4 space-y-2">
                      {rep.indicators.map((indicator) => (
                        <div key={indicator.name}>
                          <div className="flex items-center justify-between text-[11px]">
                            <span className="truncate text-slate-600 dark:text-slate-400">
                              {indicator.label}
                            </span>
                            <span className="font-semibold tabular-nums text-slate-700 dark:text-slate-200">
                              {indicator.score}
                            </span>
                          </div>
                          <div className="mt-1">
                            <ProgressBar value={indicator.score} />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Recommended next action */}
                  {rep.recommendations.length > 0 && (
                    <div className="mt-4 border-t border-slate-100 pt-3 dark:border-slate-800">
                      <p className="text-overline text-slate-500 dark:text-slate-400">
                        Önerilen aksiyon
                      </p>
                      <p className="mt-1 line-clamp-2 text-[12px] leading-5 text-slate-700 dark:text-slate-200">
                        {rep.recommendations[0]}
                      </p>
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Plans List */}
      <div>
        <h2 className="mb-3 text-heading-3 text-slate-900 dark:text-white">
          {t('coaching.section_plans')}
        </h2>
        {isPlansLoading ? (
          <Skeleton variant="card" count={2} />
        ) : plans.length === 0 ? (
          <div className="rounded-2xl border border-slate-200 bg-white py-2 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
            <EmptyState
              variant="default"
              title={t('coaching.plans_empty')}
              description="Henüz aktif koçluk planı yok. Bir temsilci seçip ilk koçluk planını oluşturarak gelişim takibi başlatın."
              action={
                <Button onClick={() => setShowCreatePlan(true)} variant="secondary">
                  İlk Koçluk Planını Oluştur
                </Button>
              }
            />
          </div>
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
                      <p className="font-medium text-slate-900 dark:text-white">{plan.user_name}</p>
                      <Badge variant={statusVariant}>
                        {translateCoachingPlanStatus(plan.status, t)}
                      </Badge>
                    </div>

                    {/* Meta */}
                    <div className="flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400">
                      <span>{t('coaching.weeks_short').replace('{n}', String(plan.weeks))}</span>
                      {plan.start_date && (
                        <span>
                          {t('coaching.start_prefix').replace(
                            '{date}',
                            formatDateTime(plan.start_date),
                          )}
                        </span>
                      )}
                    </div>

                    {/* Progress */}
                    {currentWeek !== null && (
                      <div>
                        <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 mb-1">
                          <span>{t('coaching.progress')}</span>
                          <span>
                            {t('coaching.progress_weeks')
                              .replace('{current}', String(currentWeek))
                              .replace('{total}', String(plan.weeks))
                              .replace(
                                '{pct}',
                                String(Math.round((currentWeek / plan.weeks) * 100)),
                              )}
                          </span>
                        </div>
                        <ProgressBar value={currentWeek} max={plan.weeks} />
                      </div>
                    )}

                    {/* Goals */}
                    {parsedGoals.length > 0 && (
                      <div className="border-t border-slate-100 dark:border-slate-800 pt-2">
                        <p className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-slate-400">
                          {t('coaching.goals')}
                        </p>
                        <ul className="space-y-1">
                          {parsedGoals.slice(0, 3).map((g, idx) => (
                            <li
                              key={idx}
                              className="flex items-start justify-between gap-2 text-xs"
                            >
                              <span className="text-slate-600 dark:text-slate-400 flex-1">
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
                            <li className="text-xs text-slate-400">
                              {t('coaching.goals_more').replace(
                                '{n}',
                                String(parsedGoals.length - 3),
                              )}
                            </li>
                          )}
                        </ul>
                      </div>
                    )}

                    <p className="text-xs text-slate-400 dark:text-slate-500">
                      {t('coaching.created_prefix').replace(
                        '{date}',
                        formatDateTime(plan.created_at),
                      )}
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
        title={t('coaching.modal_create_title')}
      >
        <form onSubmit={handleCreatePlan} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              {t('coaching.label_rep')}
            </label>
            <select
              className="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white"
              value={planForm.user_id}
              onChange={(e) => setPlanForm({ ...planForm, user_id: e.target.value })}
              required
            >
              <option value="">{t('coaching.select_rep')}</option>
              {reps.map((rep) => (
                <option key={rep.user_id} value={rep.user_id}>
                  {rep.user_name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
              {t('coaching.label_goals')}
            </label>
            <div className="space-y-2">
              {goalRows.map((row, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <Input
                    placeholder={t('coaching.goal_placeholder')}
                    value={row.goal}
                    onChange={(e) => handleGoalRowChange(idx, 'goal', e.target.value)}
                  />
                  <Input
                    placeholder={t('coaching.target_placeholder')}
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
                      {t('common.delete')}
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
              {t('coaching.add_goal')}
            </Button>
          </div>
          <Input
            label={t('coaching.label_duration_weeks')}
            type="number"
            value={planForm.weeks}
            onChange={(e) => setPlanForm({ ...planForm, weeks: Number(e.target.value) })}
            required
          />
          <Input
            label={t('coaching.label_start_date')}
            type="date"
            value={planForm.start_date}
            onChange={(e) => setPlanForm({ ...planForm, start_date: e.target.value })}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setShowCreatePlan(false)} type="button">
              {t('common.cancel')}
            </Button>
            <Button type="submit" loading={createPlanMutation.isPending}>
              {t('common.create')}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
