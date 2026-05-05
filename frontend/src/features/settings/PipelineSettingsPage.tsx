import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm, useFieldArray } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { toast } from 'sonner';
import { GitBranch, Plus, Trash2, Star, Pencil, Check } from 'lucide-react';
import { pipelinesApi } from '../../lib/api';
import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { Modal } from '../../components/ui/Modal';
import { useT } from '../../hooks/useT';
import { EmptyState } from '../../components/ui/EmptyState';
import type { Pipeline } from '../../lib/types';

// ── Schemas ──────────────────────────────────────────

type PipelineFormData = z.infer<ReturnType<typeof buildPipelineSchema>>;

function buildPipelineSchema(t: ReturnType<typeof useT>) {
  const stageSchema = z.object({
    key: z.string().min(1, t('pipelines.validation_key_required')),
    label: z.string().min(1, t('pipelines.validation_label_required')),
    probability: z.number().min(0).max(100),
  });

  return z.object({
    name: z.string().min(1, t('pipelines.validation_name_required')),
    description: z.string().optional(),
    is_default: z.boolean().optional(),
    stages: z.array(stageSchema),
  });
}

// ── Stage Helper ─────────────────────────────────────

// Standardised stage keys used across V4/V5/V6 pipelines. Manager picks
// from this list when adding a stage so the analytics layer always
// recognises the value (UAT item #27).
const STAGE_KEY_OPTIONS = [
  { value: 'prospecting', label: 'Araştırma (prospecting)' },
  { value: 'qualified', label: 'Yeterlilik (qualified)' },
  { value: 'proposal', label: 'Teklif (proposal)' },
  { value: 'negotiation', label: 'Müzakere (negotiation)' },
  { value: 'closed_won', label: 'Kazanıldı (closed_won)' },
  { value: 'closed_lost', label: 'Kaybedildi (closed_lost)' },
] as const;

function parseStages(
  stagesJson: string | undefined,
): { key: string; label: string; probability: number }[] {
  if (!stagesJson) return [];
  try {
    const parsed = JSON.parse(stagesJson);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

// ── Modal ─────────────────────────────────────────────

interface PipelineModalProps {
  pipeline?: Pipeline | null;
  onClose: () => void;
}

function PipelineModal({ pipeline, onClose }: PipelineModalProps) {
  const t = useT();
  const queryClient = useQueryClient();
  const isEdit = !!pipeline;
  const pipelineSchema = buildPipelineSchema(t);

  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<PipelineFormData>({
    resolver: zodResolver(pipelineSchema),
    defaultValues: {
      name: pipeline?.name ?? '',
      description: pipeline?.description ?? '',
      is_default: pipeline?.is_default ?? false,
      stages:
        parseStages(pipeline?.stages_json).length > 0
          ? parseStages(pipeline?.stages_json)
          : [{ key: 'prospecting', label: 'Araştırma', probability: 10 }],
    },
  });

  const { fields, append, remove } = useFieldArray({ control, name: 'stages' });

  const createMutation = useMutation({
    mutationFn: (values: PipelineFormData) =>
      pipelinesApi.create({
        name: values.name,
        description: values.description,
        is_default: values.is_default,
        stages_json: JSON.stringify(values.stages),
      }),
    onSuccess: () => {
      toast.success(t('pipelines.toast_created'));
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
      onClose();
    },
    onError: () => toast.error(t('pipelines.toast_create_failed')),
  });

  const updateMutation = useMutation({
    mutationFn: (values: PipelineFormData) =>
      pipelinesApi.update(pipeline!.id, {
        name: values.name,
        description: values.description,
        is_default: values.is_default,
        stages_json: JSON.stringify(values.stages),
      }),
    onSuccess: () => {
      toast.success(t('pipelines.toast_updated'));
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
      onClose();
    },
    onError: () => toast.error(t('pipelines.toast_update_failed')),
  });

  const onSubmit = (values: PipelineFormData) => {
    if (isEdit) {
      updateMutation.mutate(values);
    } else {
      createMutation.mutate(values);
    }
  };

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <Modal
      isOpen
      onClose={onClose}
      title={isEdit ? t('pipelines.modal_edit_title') : t('pipelines.modal_create_title')}
      size="lg"
    >
      <form onSubmit={handleSubmit(onSubmit)}>
        <div className="space-y-4">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              {t('pipelines.name_label')} <span className="text-red-400">*</span>
            </label>
            <input
              {...register('name')}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-honeywell-red dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              placeholder={t('pipelines.name_placeholder')}
            />
            {errors.name && <p className="mt-1 text-xs text-red-400">{errors.name.message}</p>}
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              {t('pipelines.description_label')}
            </label>
            <textarea
              {...register('description')}
              rows={2}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-honeywell-red resize-none dark:border-slate-700 dark:bg-slate-800 dark:text-white"
              placeholder={t('pipelines.description_placeholder')}
            />
          </div>

          {/* Is Default */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              {...register('is_default')}
              className="rounded border-slate-200 text-honeywell-red focus:ring-honeywell-red"
            />
            <span className="text-sm text-slate-700 dark:text-slate-300">
              {t('pipelines.default_label')}
            </span>
          </label>

          {/* Stages */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-slate-700 dark:text-slate-300">
                {t('pipelines.stages')}
              </label>
              <button
                type="button"
                onClick={() => append({ key: '', label: '', probability: 50 })}
                className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-500/10 transition-colors"
              >
                <Plus size={14} />
                {t('pipelines.add_stage')}
              </button>
            </div>

            <div className="space-y-2">
              {fields.map((field, index) => (
                <div
                  key={field.id}
                  className="flex items-center gap-2 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-slate-800 dark:bg-slate-800/50"
                >
                  <div className="flex-1 grid grid-cols-3 gap-2">
                    <div>
                      <select
                        {...register(`stages.${index}.key`)}
                        className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-honeywell-red dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      >
                        <option value="">
                          {t('pipelines.stage_key_placeholder')}
                        </option>
                        {STAGE_KEY_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                      {errors.stages?.[index]?.key && (
                        <p className="mt-0.5 text-[10px] text-red-400">
                          {errors.stages[index]?.key?.message}
                        </p>
                      )}
                    </div>
                    <div>
                      <input
                        {...register(`stages.${index}.label`)}
                        placeholder={t('pipelines.stage_label_placeholder')}
                        className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-honeywell-red dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      />
                      {errors.stages?.[index]?.label && (
                        <p className="mt-0.5 text-[10px] text-red-400">
                          {errors.stages[index]?.label?.message}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        {...register(`stages.${index}.probability`, { valueAsNumber: true })}
                        placeholder={t('pipelines.stage_probability_placeholder')}
                        min={0}
                        max={100}
                        className="w-full rounded border border-slate-200 px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-honeywell-red dark:border-slate-700 dark:bg-slate-800 dark:text-white"
                      />
                      <span className="text-xs text-slate-500 shrink-0">%</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => remove(index)}
                    className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-500/10 dark:hover:text-red-400 transition-colors"
                    disabled={fields.length === 1}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>

            <p className="mt-1.5 text-[11px] text-slate-500">{t('pipelines.stage_help')}</p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 mt-6">
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button type="submit" loading={isPending}>
            <Check size={16} />
            {isPending
              ? t('pipelines.saving')
              : isEdit
                ? t('pipelines.update')
                : t('common.create')}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ── Pipeline Card ─────────────────────────────────────

/**
 * Stage tone palette used by the inline stage preview row.
 *
 * Six discrete tones cycle if a pipeline has more stages; the dot lives on
 * a slate chip so the row stays calm and only carries enough color to show
 * stage progression.
 */
const STAGE_TONES = [
  { dot: 'bg-slate-400', chip: 'bg-slate-100 text-slate-700 ring-slate-200' },
  { dot: 'bg-blue-500', chip: 'bg-blue-50 text-blue-700 ring-blue-100' },
  { dot: 'bg-violet-500', chip: 'bg-violet-50 text-violet-700 ring-violet-100' },
  { dot: 'bg-amber-500', chip: 'bg-amber-50 text-amber-800 ring-amber-100' },
  { dot: 'bg-orange-500', chip: 'bg-orange-50 text-orange-800 ring-orange-100' },
  { dot: 'bg-emerald-500', chip: 'bg-emerald-50 text-emerald-700 ring-emerald-100' },
];

interface PipelineCardProps {
  pipeline: Pipeline;
  onEdit: () => void;
  onDelete: () => void;
  onSetDefault: () => void;
}

function PipelineCard({ pipeline, onEdit, onDelete, onSetDefault }: PipelineCardProps) {
  const t = useT();
  const stages = parseStages(pipeline.stages_json);
  const visibleStages = stages.slice(0, 4);
  const overflow = stages.length - visibleStages.length;

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-(--shadow-xs) transition-all hover:-translate-y-px hover:border-honeywell-red/30 hover:shadow-(--shadow-sm) dark:border-slate-800 dark:bg-slate-900">
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <button
            type="button"
            onClick={onEdit}
            className="flex min-w-0 flex-1 items-start gap-3 text-left"
          >
            <span className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-honeywell-red/10 text-honeywell-red ring-1 ring-inset ring-honeywell-red/20">
              <GitBranch size={18} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="truncate text-[14px] font-semibold text-slate-900 dark:text-white">
                  {pipeline.name}
                </h3>
                {pipeline.is_default && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-700 ring-1 ring-inset ring-amber-100 dark:bg-amber-950/30 dark:text-amber-300 dark:ring-amber-900/40">
                    <Star size={10} fill="currentColor" />
                    {t('pipelines.default_badge')}
                  </span>
                )}
              </div>
              {pipeline.description && (
                <p className="mt-1 line-clamp-1 text-[12px] text-slate-500 dark:text-slate-400">
                  {pipeline.description}
                </p>
              )}
              <p className="mt-1.5 text-[11px] tabular-nums text-slate-400 dark:text-slate-500">
                {stages.length} {t('pipelines.stage_count_suffix')}
              </p>
            </div>
          </button>
        </div>

        {/* Stage preview row — visualizes the pipeline as labeled chips so a
            "6 aşama" line becomes glanceable. Tones cycle through STAGE_TONES;
            beyond 4 stages we collapse the rest into a "+N" pill. */}
        {stages.length > 0 && (
          <div className="mt-4 flex flex-wrap items-center gap-1.5">
            {visibleStages.map((stage, idx) => {
              const tone = STAGE_TONES[idx % STAGE_TONES.length];
              return (
                <span
                  key={stage.key + idx}
                  className={[
                    'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset',
                    tone.chip,
                  ].join(' ')}
                  title={`${stage.label} · ${stage.probability}%`}
                >
                  <span className={`inline-block h-1.5 w-1.5 rounded-full ${tone.dot}`} />
                  <span className="truncate">{stage.label}</span>
                </span>
              );
            })}
            {overflow > 0 && (
              <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-bold tabular-nums text-slate-600 ring-1 ring-inset ring-slate-200 dark:bg-slate-800 dark:text-slate-300 dark:ring-slate-700">
                +{overflow}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Action row — pinned to the bottom-right so card body stays clean.
          "Varsayılan yap" only renders for non-default pipelines. */}
      <div className="flex items-center justify-end gap-1.5 border-t border-slate-100 bg-slate-50/50 px-4 py-2.5 dark:border-slate-800 dark:bg-slate-900/40">
        {!pipeline.is_default && (
          <Button
            variant="tertiary"
            size="sm"
            onClick={onSetDefault}
            title={t('pipelines.set_default')}
          >
            <Star size={13} />
            {t('pipelines.set_default')}
          </Button>
        )}
        <Button variant="tertiary" size="sm" onClick={onEdit} title={t('common.edit')}>
          <Pencil size={13} />
          {t('common.edit')}
        </Button>
        {!pipeline.is_default && (
          <Button variant="ghost" size="sm" onClick={onDelete} aria-label={t('common.delete')}>
            <Trash2 size={13} className="text-red-500" />
          </Button>
        )}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────

export default function PipelineSettingsPage() {
  const t = useT();
  const queryClient = useQueryClient();
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<Pipeline | null>(null);

  const {
    data: pipelines = [],
    isLoading,
    isError,
  } = useQuery<Pipeline[]>({
    queryKey: ['pipelines'],
    queryFn: async () => {
      const res = await pipelinesApi.list();
      // Round-5 Phase 7 — backend canonicalized to ``items``; legacy
      // ``pipelines`` retained server-side as additive bridge.
      return res?.items ?? res?.pipelines ?? (Array.isArray(res) ? res : []);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => pipelinesApi.delete(id),
    onSuccess: () => {
      toast.success(t('pipelines.toast_deleted'));
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
    },
    onError: () => toast.error(t('pipelines.toast_delete_failed')),
  });

  const setDefaultMutation = useMutation({
    mutationFn: (id: number) => pipelinesApi.setDefault(id),
    onSuccess: () => {
      toast.success(t('pipelines.toast_default_updated'));
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
    },
    onError: () => toast.error(t('settings.operation_failed')),
  });

  const handleEdit = (pipeline: Pipeline) => {
    setEditTarget(pipeline);
    setIsCreateOpen(true);
  };

  const handleNew = () => {
    setEditTarget(null);
    setIsCreateOpen(true);
  };

  const handleCloseModal = () => {
    setIsCreateOpen(false);
    setEditTarget(null);
  };

  if (isError) {
    return (
      <div className="space-y-6">
        <PageHeader title={t('pipelines.title')} description={t('pipelines.description')} />
        <Card>
          <div className="p-8 text-center">
            <p className="text-sm text-red-500">{t('pipelines.load_error')}</p>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader title={t('pipelines.title')} description={t('pipelines.description')}>
        <Button onClick={handleNew}>
          <Plus size={16} />
          {t('pipelines.new')}
        </Button>
      </PageHeader>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {[1, 2, 3, 4].map((n) => (
            <div
              key={n}
              className="h-[160px] animate-pulse rounded-2xl bg-slate-100 dark:bg-slate-800"
            />
          ))}
        </div>
      ) : pipelines.length === 0 ? (
        <div className="rounded-2xl border border-slate-200 bg-white py-2 shadow-(--shadow-xs) dark:border-slate-800 dark:bg-slate-900">
          <EmptyState
            variant="default"
            icon={<GitBranch size={20} />}
            title={t('pipelines.empty_title')}
            description={t('pipelines.empty_body')}
            action={
              <Button onClick={handleNew} variant="secondary">
                <Plus size={14} />
                {t('pipelines.empty_cta')}
              </Button>
            }
          />
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {pipelines.map((pipeline) => (
            <PipelineCard
              key={pipeline.id}
              pipeline={pipeline}
              onEdit={() => handleEdit(pipeline)}
              onDelete={() => deleteMutation.mutate(pipeline.id)}
              onSetDefault={() => setDefaultMutation.mutate(pipeline.id)}
            />
          ))}
        </div>
      )}

      {isCreateOpen && <PipelineModal pipeline={editTarget} onClose={handleCloseModal} />}
    </div>
  );
}
