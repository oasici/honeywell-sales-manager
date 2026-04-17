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
import type { Pipeline } from '../../lib/types';

// ── Schemas ──────────────────────────────────────────

const stageSchema = z.object({
  key: z.string().min(1, 'Anahtar zorunlu'),
  label: z.string().min(1, 'Etiket zorunlu'),
  probability: z.number().min(0).max(100),
});

const pipelineSchema = z.object({
  name: z.string().min(1, 'Pipeline adi zorunlu'),
  description: z.string().optional(),
  is_default: z.boolean().optional(),
  stages: z.array(stageSchema),
});

type PipelineFormData = z.infer<typeof pipelineSchema>;

// ── Stage Count Helper ────────────────────────────────

function parseStageCount(stagesJson: string | undefined): number {
  if (!stagesJson) return 0;
  try {
    const parsed = JSON.parse(stagesJson);
    return Array.isArray(parsed) ? parsed.length : 0;
  } catch {
    return 0;
  }
}

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
  const queryClient = useQueryClient();
  const isEdit = !!pipeline;

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
          : [{ key: 'prospecting', label: 'Arastirma', probability: 10 }],
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
      toast.success('Pipeline oluşturuldu');
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
      onClose();
    },
    onError: () => toast.error('Pipeline oluşturulamadı'),
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
      toast.success('Pipeline guncellendi');
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
      onClose();
    },
    onError: () => toast.error('Pipeline guncellenemedi'),
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
    <Modal isOpen onClose={onClose} title={isEdit ? 'Pipeline Düzenle' : 'Yeni Pipeline'} size="lg">
      <form onSubmit={handleSubmit(onSubmit)}>
        <div className="space-y-4">
          {/* Name */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Pipeline Adi <span className="text-red-400">*</span>
            </label>
            <input
              {...register('name')}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-honeywell-red dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              placeholder="Örneğin: Standart Satış Pipeline"
            />
            {errors.name && <p className="mt-1 text-xs text-red-400">{errors.name.message}</p>}
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Açıklama
            </label>
            <textarea
              {...register('description')}
              rows={2}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-honeywell-red resize-none dark:border-gray-600 dark:bg-gray-800 dark:text-white"
              placeholder="Bu pipeline hakkinda kısa bir açıklama..."
            />
          </div>

          {/* Is Default */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              {...register('is_default')}
              className="rounded border-gray-300 text-honeywell-red focus:ring-honeywell-red"
            />
            <span className="text-sm text-gray-700 dark:text-gray-300">
              Varsayılan Pipeline olarak ayarla
            </span>
          </label>

          {/* Stages */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Aşamalar
              </label>
              <button
                type="button"
                onClick={() => append({ key: '', label: '', probability: 50 })}
                className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-500/10 transition-colors"
              >
                <Plus size={14} />
                Aşama Ekle
              </button>
            </div>

            <div className="space-y-2">
              {fields.map((field, index) => (
                <div
                  key={field.id}
                  className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-700 dark:bg-gray-800/50"
                >
                  <div className="flex-1 grid grid-cols-3 gap-2">
                    <div>
                      <input
                        {...register(`stages.${index}.key`)}
                        placeholder="anahtar"
                        className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-honeywell-red dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                      />
                      {errors.stages?.[index]?.key && (
                        <p className="mt-0.5 text-[10px] text-red-400">
                          {errors.stages[index]?.key?.message}
                        </p>
                      )}
                    </div>
                    <div>
                      <input
                        {...register(`stages.${index}.label`)}
                        placeholder="Etiket"
                        className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-honeywell-red dark:border-gray-600 dark:bg-gray-800 dark:text-white"
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
                        placeholder="%"
                        min={0}
                        max={100}
                        className="w-full rounded border border-gray-300 px-2 py-1.5 text-xs focus:outline-none focus:ring-1 focus:ring-honeywell-red dark:border-gray-600 dark:bg-gray-800 dark:text-white"
                      />
                      <span className="text-xs text-gray-500 shrink-0">%</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => remove(index)}
                    className="rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-500/10 dark:hover:text-red-400 transition-colors"
                    disabled={fields.length === 1}
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              ))}
            </div>

            <p className="mt-1.5 text-[11px] text-gray-500">
              Her aşama için benzersiz bir anahtar, goruntulenen etiket ve kapanma olasiligi girin.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 mt-6">
          <Button type="button" variant="secondary" onClick={onClose}>
            İptal
          </Button>
          <Button type="submit" loading={isPending}>
            <Check size={16} />
            {isPending ? 'Kaydediliyor...' : isEdit ? 'Güncelle' : 'Oluştur'}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ── Pipeline Card ─────────────────────────────────────

interface PipelineCardProps {
  pipeline: Pipeline;
  onEdit: () => void;
  onDelete: () => void;
  onSetDefault: () => void;
}

function PipelineCard({ pipeline, onEdit, onDelete, onSetDefault }: PipelineCardProps) {
  const stageCount = parseStageCount(pipeline.stages_json);

  return (
    <Card className="cursor-pointer hover:ring-2 hover:ring-blue-400/30 transition-all">
      <div className="p-5">
        <div className="flex items-start justify-between gap-4">
          <button
            type="button"
            onClick={onEdit}
            className="flex items-center gap-3 min-w-0 text-left cursor-pointer"
          >
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-500/15">
              <GitBranch size={20} className="text-blue-400" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                  {pipeline.name}
                </h3>
                {pipeline.is_default && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-amber-400/15 px-2 py-0.5 text-[10px] font-semibold text-amber-500">
                    <Star size={10} />
                    Varsayılan
                  </span>
                )}
              </div>
              {pipeline.description && (
                <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400 truncate">
                  {pipeline.description}
                </p>
              )}
              <p className="mt-1 text-xs text-gray-400">{stageCount} aşama</p>
            </div>
          </button>

          <div className="flex items-center gap-1 shrink-0">
            {!pipeline.is_default && (
              <button
                onClick={onSetDefault}
                title="Varsayılan Yap"
                className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-medium text-gray-500 hover:bg-amber-500/10 hover:text-amber-500 dark:text-gray-400 transition-colors"
              >
                <Star size={14} />
                Varsayılan Yap
              </button>
            )}
            <button
              onClick={onEdit}
              title="Düzenle"
              className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-white/5 hover:text-gray-800 dark:hover:text-white transition-colors"
            >
              <Pencil size={15} />
            </button>
            {!pipeline.is_default && (
              <button
                onClick={onDelete}
                title="Sil"
                className="rounded-lg p-1.5 text-gray-500 hover:bg-red-50 dark:hover:bg-red-500/10 hover:text-red-600 dark:hover:text-red-400 transition-colors"
              >
                <Trash2 size={15} />
              </button>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}

// ── Page ──────────────────────────────────────────────

export default function PipelineSettingsPage() {
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
      return res?.pipelines ?? res?.items ?? (Array.isArray(res) ? res : []);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => pipelinesApi.delete(id),
    onSuccess: () => {
      toast.success('Pipeline silindi');
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
    },
    onError: () => toast.error('Pipeline silinemedi'),
  });

  const setDefaultMutation = useMutation({
    mutationFn: (id: number) => pipelinesApi.setDefault(id),
    onSuccess: () => {
      toast.success('Varsayılan pipeline guncellendi');
      queryClient.invalidateQueries({ queryKey: ['pipelines'] });
    },
    onError: () => toast.error('İşlem başarısız'),
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
        <PageHeader
          title="Pipeline Ayarlari"
          description="Satış pipeline'larinizi ve asamalarini yonetin"
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
        title="Pipeline Ayarlari"
        description="Satış pipeline'larinizi ve asamalarini yonetin"
      >
        <Button onClick={handleNew}>
          <Plus size={16} />
          Yeni Pipeline
        </Button>
      </PageHeader>

      {isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-24 rounded-2xl bg-gray-100 dark:bg-gray-800 animate-pulse" />
          ))}
        </div>
      ) : pipelines.length === 0 ? (
        <div className="rounded-2xl border-2 border-dashed border-gray-200 dark:border-gray-700 py-16 text-center">
          <GitBranch className="mx-auto mb-3 text-gray-300 dark:text-gray-600" size={32} />
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">Henüz pipeline yok</p>
          <p className="mt-1 text-xs text-gray-400">
            Satış sureclerinizi yonetmek için yeni bir pipeline olusturun.
          </p>
          <Button onClick={handleNew} className="mt-4">
            <Plus size={14} />
            Ilk Pipeline'i Oluştur'          </Button>
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
