import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { PageHeader } from '../../components/ui/PageHeader';
import { Button } from '../../components/ui/Button';
import { Input } from '../../components/ui/Input';
import { Card } from '../../components/ui/Card';
import { Skeleton } from '../../components/ui/Skeleton';
import { engagementApi, emailTemplatesApi } from '../../lib/api';
import type { Sequence } from '../../lib/types';
import { useT } from '../../hooks/useT';

interface SequenceStep {
  step: number;
  action: string;
  delay_days: number;
  template: string;
  email_template_id?: number | null;
}

function htmlToPlainText(html: string): string {
  if (typeof document === 'undefined') {
    return html
      .replace(/<[^>]+>/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }
  const d = document.createElement('div');
  d.innerHTML = html;
  return (d.textContent || d.innerText || '').replace(/\s+/g, ' ').trim();
}

const ACTION_OPTIONS = [
  { value: 'email', label: 'Email' },
  { value: 'task', label: 'Görev' },
  { value: 'wait', label: 'Bekleme' },
];

// Template presets keyed by ?template=<slug> in the URL — must match
// the slugs surfaced from SequencesPage.SEQUENCE_TEMPLATES so the
// "Bu şablonu kullan" CTA pre-fills the builder (V9 UAT #24).
interface TemplatePreset {
  name: string;
  description: string;
  steps: SequenceStep[];
}

const TEMPLATE_PRESETS: Record<string, TemplatePreset> = {
  'lead-welcome': {
    name: 'Yeni Lead Karşılama',
    description: '5 adımda yeni leadi tanıt, ihtiyacını öğren ve demo gününe yönlendir.',
    steps: [
      {
        step: 1,
        action: 'email',
        delay_days: 0,
        template: 'Merhaba {first_name}, aramıza hoş geldin!',
      },
      {
        step: 2,
        action: 'task',
        delay_days: 1,
        template: 'İlk arama: müşteri ihtiyaçlarını dinle ve uygunluğu doğrula.',
      },
      {
        step: 3,
        action: 'email',
        delay_days: 3,
        template: 'Vakit bulduğunda demo planlayalım — uygun saatlerini paylaşır mısın?',
      },
      { step: 4, action: 'wait', delay_days: 2, template: '' },
      {
        step: 5,
        action: 'email',
        delay_days: 0,
        template: 'Hâlâ cevap alamadık — son bir hatırlatma yollamak istedik.',
      },
    ],
  },
  'post-quote-followup': {
    name: 'Teklif Sonrası Takip',
    description: 'Teklif gönderdikten sonra sırasıyla onay, soru-cevap ve müzakere takibi yap.',
    steps: [
      {
        step: 1,
        action: 'email',
        delay_days: 0,
        template: 'Teklifimizi inceleyebildin mi? Sorularını yanıtlamaktan memnuniyet duyarız.',
      },
      {
        step: 2,
        action: 'task',
        delay_days: 2,
        template: 'Telefon takibi: itirazları öğren, öncelik sırasını netleştir.',
      },
      {
        step: 3,
        action: 'email',
        delay_days: 4,
        template: 'Teklifte revize istediğin bir nokta var mı?',
      },
      {
        step: 4,
        action: 'task',
        delay_days: 6,
        template: 'Karar tarihini netleştir; gerekirse müzakere için yöneticiyi dahil et.',
      },
    ],
  },
  'win-back': {
    name: 'Riskli Müşteri Geri Kazanım',
    description:
      'Health skoru düşen hesaplara değer hatırlatma, başarı hikayesi ve özel teklifle ulaş.',
    steps: [
      {
        step: 1,
        action: 'email',
        delay_days: 0,
        template: 'Seninle uzun süredir konuşamadık — son durum nedir?',
      },
      {
        step: 2,
        action: 'email',
        delay_days: 5,
        template: 'Benzer bir müşteride elde ettiğimiz başarı hikayesini paylaşmak isteriz.',
      },
      {
        step: 3,
        action: 'task',
        delay_days: 9,
        template: 'Yenileme görüşmesi planla — özel kampanya teklifini hazırla.',
      },
    ],
  },
};

const EMPTY_STEP: SequenceStep = {
  step: 1,
  action: 'email',
  delay_days: 0,
  template: '',
};

export default function SequenceBuilderPage() {
  const t = useT();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const isEdit = Boolean(id);
  const sequenceId = id ? Number(id) : null;
  const templateSlug = searchParams.get('template');

  // Pre-fill from template preset when ?template=slug present and no
  // existing sequence is being edited (V9 UAT #24).
  const initialPreset = !isEdit && templateSlug ? TEMPLATE_PRESETS[templateSlug] : undefined;

  const [name, setName] = useState(initialPreset?.name ?? '');
  const [description, setDescription] = useState(initialPreset?.description ?? '');
  const [steps, setSteps] = useState<SequenceStep[]>(
    initialPreset && initialPreset.steps.length > 0
      ? initialPreset.steps.map((s) => ({ ...s }))
      : [{ ...EMPTY_STEP }],
  );
  const [isAutoEnroll, setIsAutoEnroll] = useState(false);
  const [scoreThreshold, setScoreThreshold] = useState(50);

  const { data: sequence, isLoading } = useQuery<Sequence>({
    queryKey: ['sequence', sequenceId],
    queryFn: () => engagementApi.getSequence(sequenceId!),
    enabled: Boolean(sequenceId),
  });

  const { data: emailTplData } = useQuery({
    queryKey: ['email-templates', 'sequence-builder'],
    queryFn: () => emailTemplatesApi.list(),
  });
  const emailTemplates = (emailTplData?.items ?? []) as Array<{
    id: number;
    name: string;
    subject: string;
    body_html: string;
  }>;

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
              email_template_id:
                typeof s.email_template_id === 'number' ? s.email_template_id : null,
            })),
          );
        }
        if (sequence.auto_enroll_rules) {
          setIsAutoEnroll(true);
          // R4-TS-5 widened auto_enroll_rules to dict | array | null.
          // The score_threshold legacy lives only on the dict shape;
          // narrow before reading and fall back to the default.
          const rules = sequence.auto_enroll_rules;
          const threshold =
            !Array.isArray(rules) && rules && typeof rules === 'object'
              ? (rules as Record<string, unknown>).score_threshold
              : null;
          setScoreThreshold(typeof threshold === 'number' ? threshold : 50);
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
      toast.success(isEdit ? 'Sekans güncellendi' : 'Sekans oluşturuldu');
      queryClient.invalidateQueries({ queryKey: ['sequences'] });
      navigate('/engagement/sequences');
    },
    onError: () => toast.error('Kaydetme başarısız'),
  });

  const addStep = useCallback(() => {
    setSteps((prev) => [...prev, { ...EMPTY_STEP, step: prev.length + 1 }]);
  }, []);

  const removeStep = useCallback((index: number) => {
    setSteps((prev) => prev.filter((_, i) => i !== index).map((s, i) => ({ ...s, step: i + 1 })));
  }, []);

  const updateStep = useCallback(
    (index: number, field: keyof SequenceStep, value: string | number | null) => {
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
      toast.error('En az bir adım ekleyin');
      return;
    }

    const payload: Record<string, unknown> = {
      name,
      description: description || undefined,
      steps: steps.map((s) => {
        const row: Record<string, unknown> = {
          step: s.step,
          action: s.action,
          delay_days: s.delay_days,
          template: s.template,
        };
        if (s.email_template_id != null) {
          row.email_template_id = s.email_template_id;
        }
        return row;
      }),
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
        title={isEdit ? 'Sekans Düzenle' : 'Yeni Sekans Oluştur'}
        description="Adım adım takip sekansini tanimlayin"
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
              placeholder="Örneğin: Teklif Takibi"
            />
            <Input
              label="Açıklama"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Sekans aciklamasi"
            />
          </div>
        </Card>

        {/* Steps */}
        <Card title="Adımlar">
          <div className="relative space-y-0">
            {steps.map((step, idx) => (
              <div key={idx} className="relative flex gap-4">
                {/* Vertical connector */}
                <div className="flex flex-col items-center">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white">
                    {idx + 1}
                  </div>
                  {idx < steps.length - 1 && (
                    <div className="w-0.5 flex-1 border-l-2 border-dashed border-slate-200" />
                  )}
                </div>

                {/* Step card */}
                <div className="mb-4 flex-1 rounded-lg border border-slate-200 bg-slate-50 p-4">
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                    <div>
                      <label className="mb-1 block text-xs font-medium text-slate-600">Tur</label>
                      <select
                        value={step.action}
                        onChange={(e) => updateStep(idx, 'action', e.target.value)}
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                      >
                        {ACTION_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>
                            {opt.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="mb-1 block text-xs font-medium text-slate-600">
                        Gecikme (gun)
                      </label>
                      <input
                        type="number"
                        min={0}
                        value={step.delay_days}
                        onChange={(e) => updateStep(idx, 'delay_days', Number(e.target.value))}
                        className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100"
                      />
                    </div>
                    <div className="flex items-end">
                      <button
                        type="button"
                        onClick={() => removeStep(idx)}
                        disabled={steps.length <= 1}
                        className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                          steps.length <= 1
                            ? 'cursor-not-allowed bg-slate-100 text-slate-400'
                            : 'bg-red-50 text-red-600 hover:bg-red-100'
                        }`}
                      >
                        Sil
                      </button>
                    </div>
                  </div>
                  <div className="mt-3 space-y-2">
                    {step.action === 'email' ? (
                      <div>
                        <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">
                          {t('sequences.builder_email_tpl')}
                        </label>
                        <select
                          className="w-full rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 px-3 py-2 text-sm"
                          value={step.email_template_id ?? ''}
                          onChange={(e) => {
                            const raw = e.target.value;
                            if (!raw) {
                              updateStep(idx, 'email_template_id', null);
                              return;
                            }
                            const tid = Number(raw);
                            const tpl = emailTemplates.find((x) => x.id === tid);
                            if (tpl) {
                              const body = htmlToPlainText(tpl.body_html || '');
                              const merged = `${tpl.subject}\n\n${body}`.trim();
                              setSteps((prev) =>
                                prev.map((s, i) =>
                                  i === idx
                                    ? { ...s, email_template_id: tid, template: merged }
                                    : s,
                                ),
                              );
                            }
                          }}
                        >
                          <option value="">{t('sequences.builder_email_tpl_none')}</option>
                          {emailTemplates.map((tpl) => (
                            <option key={tpl.id} value={tpl.id}>
                              {tpl.name}
                            </option>
                          ))}
                        </select>
                        <p className="mt-1 text-[11px] text-slate-500">
                          {t('sequences.builder_email_tpl_hint')}
                        </p>
                      </div>
                    ) : null}
                    <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-slate-400">
                      Şablon / İçerik
                    </label>
                    <textarea
                      rows={3}
                      value={step.template}
                      onChange={(e) => updateStep(idx, 'template', e.target.value)}
                      placeholder="Email şablonu veya gorev aciklamasi..."
                      className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm shadow-sm outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-100 dark:border-slate-700 dark:bg-slate-800"
                    />
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-4">
            <Button variant="secondary" onClick={addStep}>
              Adım Ekle
            </Button>
          </div>
        </Card>

        {/* Auto-enroll */}
        <Card title="Otomatik Kayıt">
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isAutoEnroll}
                onChange={(e) => setIsAutoEnroll(e.target.checked)}
                className="h-4 w-4 rounded border-slate-200 text-blue-600 focus:ring-blue-500"
              />
              Otomatik kayıt kurallarını etkinleştir
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
                <p className="mt-1 text-xs text-slate-500">
                  Bu skor değerini aşan leadler otomatik olarak sekansa kaydedilir.
                </p>
              </div>
            )}
          </div>
        </Card>

        {/* Ready-template gallery — only surfaced when viewing an
            existing sequence so the user has a "what could I build
            next?" reference without leaving the page. New-sequence
            mode already gets templates via the empty-state on
            SequencesPage, so duplicating them here would be noise. */}
        {isEdit && (
          <Card title="Hazır Şablonlar">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(TEMPLATE_PRESETS).map(([slug, preset]) => (
                <button
                  key={slug}
                  type="button"
                  onClick={() => navigate(`/engagement/sequences/new?template=${slug}`)}
                  className="group flex h-full flex-col rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-(--shadow-xs) transition-all hover:-translate-y-px hover:border-honeywell-red/30 hover:shadow-(--shadow-sm) focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-800 dark:bg-slate-900"
                >
                  <h4 className="text-[14px] font-semibold text-slate-900 dark:text-white">
                    {preset.name}
                  </h4>
                  <p className="mt-1.5 text-[12px] leading-5 text-slate-500 dark:text-slate-400 line-clamp-3">
                    {preset.description}
                  </p>
                  <div className="mt-3 flex items-center justify-between text-[12px]">
                    <span className="tabular-nums text-slate-500 dark:text-slate-400">
                      {preset.steps.length} adım
                    </span>
                    <span className="font-medium text-honeywell-red">Bu şablondan oluştur →</span>
                  </div>
                </button>
              ))}
            </div>
            <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">
              Şablonu seçtiğinizde yeni bir sekans oluşturma sayfası açılır; mevcut sekans
              değiştirilmez.
            </p>
          </Card>
        )}
      </div>
    </div>
  );
}
