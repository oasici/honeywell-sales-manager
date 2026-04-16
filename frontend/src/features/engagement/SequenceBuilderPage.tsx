import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';
import { engagementApi } from '../../lib/api';
import type { Sequence } from '../../lib/types';

interface SequenceStep {
  step: number;
  action: string;
  delay_days: number;
  template: string;
}

const ACTION_OPTIONS = [
  { value: 'email', label: 'Email' },
  { value: 'task', label: 'Gorev' },
  { value: 'wait', label: 'Bekleme' },
];

const EMPTY_STEP: SequenceStep = {
  step: 1,
  action: 'email',
  delay_days: 0,
  template: '',
};

export default function SequenceBuilderPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isEdit = Boolean(id);
  const sequenceId = id ? Number(id) : null;

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [steps, setSteps] = useState<SequenceStep[]>([{ ...EMPTY_STEP }]);
  const [isAutoEnroll, setIsAutoEnroll] = useState(false);
  const [scoreThreshold, setScoreThreshold] = useState(50);

  const { data: sequence, isLoading } = useQuery<Sequence>({
    queryKey: ['sequence', sequenceId],
    queryFn: () => engagementApi.getSequence(sequenceId!),
    enabled: Boolean(sequenceId),
  });

  useEffect(() => {
    if (sequence) {
      queueMicrotask(() => {
        setName(sequence.name);
        setDescription(sequence.description || '');
        if (sequence.steps && sequence.steps.length > 0) {
          setSteps(
            sequence.steps.map((s, idx) => ({
              step: idx + 1,
              action: (s.action as string) || (s.type as string) || 'email',
              delay_days: (s.delay_days as number) || 0,
              template: (s.template as string) || '',
            })),
          );
        }
        if (sequence.auto_enroll_rules) {
          setIsAutoEnroll(true);
          setScoreThreshold((sequence.auto_enroll_rules.score_threshold as number) || 50);
        }
      });
    }
  }, [sequence]);

  const saveMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      isEdit
        ? engagementApi.updateSequence(sequenceId!, payload)
        : engagementApi.createSequence(payload),
    onSuccess: () => {
      toast.success(isEdit ? 'Sekans guncellendi' : 'Sekans olusturuldu');
      queryClient.invalidateQueries({ queryKey: ['sequences'] });
      navigate('/engagement/sequences');
    },
    onError: () => toast.error('Kaydetme basarisiz'),
  });

  const addStep = useCallback(() => {
    setSteps((prev) => [...prev, { ...EMPTY_STEP, step: prev.length + 1 }]);
  }, []);

  const removeStep = useCallback((index: number) => {
    setSteps((prev) => prev.filter((_, i) => i !== index).map((s, i) => ({ ...s, step: i + 1 })));
  }, []);

  const updateStep = useCallback(
    (index: number, field: keyof SequenceStep, value: string | number) => {
      setSteps((prev) => prev.map((s, i) => (i === index ? { ...s, [field]: value } : s)));
    },
    [],
  );

  function handleSave() {
    if (!name.trim()) {
      toast.error('Sekans adi zorunludur');
      return;
    }
    if (steps.length === 0) {
      toast.error('En az bir adim ekleyin');
      return;
    }

    const payload: Record<string, unknown> = {
      name,
      description: description || undefined,
      steps: steps.map((s) => ({
        step: s.step,
        action: s.action,
        delay_days: s.delay_days,
        template: s.template,
      })),
    };

    if (isAutoEnroll) {
      payload.auto_enroll_rules = { score_threshold: scoreThreshold };
    }

    saveMutation.mutate(payload);
  }

  if (isEdit && isLoading) {
    return <Skeleton variant="card" count={3} />;
  }

  return (
    <div>
      <PageHeader
        title={isEdit ? 'Sekans Duzenle' : 'Yeni Sekans Olustur'}
        description="Adim adim takip sekansini tanimlayin"
      >
        <Button variant="secondary" onClick={() => navigate('/engagement/sequences')}>
          Geri Don
        </Button>
        <Button loading={saveMutation.isPending} onClick={handleSave}>
          Kaydet
        </Button>
      </PageHeader>

      <div className="space-y-6">
        {/* Name + Description */}
        <Card title="Genel Bilgiler">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Input
              label="Sekans Adi"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ornegin: Teklif Takibi"
            />
            <Input
              label="Aciklama"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Sekans aciklamasi"
            />
          </div>
        </Card>

        {/* Steps */}
        <Card title="Adimlar">
          <div className="relative space-y-0">
            {steps.map((step, idx) => (
              <div key={idx} className="relative flex gap-4">
                {/* Vertical connector */}
                <div className="flex flex-col items-center">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white">
                    {idx + 1}
                  </div>
                  {idx < steps.length - 1 && (
                    <div className="w-0.5 flex-1 border-l-2 border-dashed border-gray-300" />
                  )}
                </div>

                {/* Step card */}
                <div className="mb-4 flex-1 rounded-lg border border-gray-200 bg-gray-50 p-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-600">Tur</label>
                      <select
                        value={step.action}
                        onChange={(e) => updateStep(idx, 'action', e.target.value)}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                      >
                        {ACTION_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-gray-600">
                        Gecikme (gun)
                      </label>
                      <input
                        type="number"
                        min={0}
                        value={step.delay_days}
                        onChange={(e) => updateStep(idx, 'delay_days', Number(e.target.value))}
                        className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                      />
                    </div>
                    <div className="flex items-end">
                      <button
                        type="button"
                        onClick={() => removeStep(idx)}
                        disabled={steps.length <= 1}
                        className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                          steps.length <= 1
                            ? 'cursor-not-allowed bg-gray-100 text-gray-400'
                            : 'bg-red-50 text-red-600 hover:bg-red-100'
                        }`}
                      >
                        Sil
                      </button>
                    </div>
                  </div>
                  <div className="mt-3">
                    <label className="mb-1 block text-xs font-medium text-gray-600">
                      Sablon / Icerik
                    </label>
                    <textarea
                      rows={3}
                      value={step.template}
                      onChange={(e) => updateStep(idx, 'template', e.target.value)}
                      placeholder="Email sablonu veya gorev aciklamasi..."
                      className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4">
            <Button variant="secondary" onClick={addStep}>
              Adim Ekle
            </Button>
          </div>
        </Card>

        {/* Auto-enroll */}
        <Card title="Otomatik Kayit">
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isAutoEnroll}
                onChange={(e) => setIsAutoEnroll(e.target.checked)}
                className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              Otomatik kayit kurallarini etkinlestir
            </label>
            {isAutoEnroll && (
              <div className="max-w-xs">
                <Input
                  label="Minimum Lead Skoru"
                  type="number"
                  min={0}
                  max={100}
                  value={scoreThreshold}
                  onChange={(e) => setScoreThreshold(Number(e.target.value))}
                />
                <p className="mt-1 text-xs text-gray-500">
                  Bu skor degerini asan leadler otomatik olarak sekansa kaydedilir.
                </p>
              </div>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
}
