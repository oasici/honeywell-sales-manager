import { useState, useEffect, useCallback } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '../../components/ui/Button';
import { Card } from '../../components/ui/Card';
import { guidedSellingApi } from '../../lib/api';
import { formatCurrency } from '../../lib/formatters';
import type { SellingGuide, SellingGuideStep, GuidedSellingSuggestion } from '../../lib/types';
import { useT } from '../../hooks/useT';

interface GuidedSellingWizardProps {
  isOpen: boolean;
  onClose: () => void;
  onComplete: (
    items: {
      spare_part_id: number;
      honeywell_code: string;
      description: string;
      quantity: number;
      unit_price: number;
      discount_pct: number;
    }[],
  ) => void;
}

type WizardPhase = 'select-guide' | 'answering' | 'results';

function tx(template: string, vars: Record<string, string | number>): string {
  return Object.entries(vars).reduce(
    (acc, [k, v]) => acc.replaceAll(`{${k}}`, String(v)),
    template,
  );
}

export default function GuidedSellingWizard({
  isOpen,
  onClose,
  onComplete,
}: GuidedSellingWizardProps) {
  const t = useT();
  const [phase, setPhase] = useState<WizardPhase>('select-guide');
  const [selectedGuideId, setSelectedGuideId] = useState<number | null>(null);
  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [suggestions, setSuggestions] = useState<GuidedSellingSuggestion | null>(null);

  const { data: guidesData, isLoading: isLoadingGuides } = useQuery({
    queryKey: ['guided-selling-guides'],
    queryFn: () => guidedSellingApi.list(),
    enabled: isOpen,
  });

  const { data: selectedGuide } = useQuery<SellingGuide>({
    queryKey: ['guided-selling-guide', selectedGuideId],
    queryFn: () => guidedSellingApi.get(selectedGuideId!),
    enabled: !!selectedGuideId,
  });

  const evaluateMutation = useMutation({
    mutationFn: (currentAnswers: Record<string, string>) =>
      guidedSellingApi.evaluate(selectedGuideId!, currentAnswers),
    onSuccess: (data) => {
      setSuggestions(data as GuidedSellingSuggestion);
    },
  });

  // Reset state when closing
  useEffect(() => {
    if (!isOpen) {
      queueMicrotask(() => {
        setPhase('select-guide');
        setSelectedGuideId(null);
        setCurrentStepIndex(0);
        setAnswers({});
        setSuggestions(null);
      });
    }
  }, [isOpen]);

  const guides: SellingGuide[] = guidesData?.guides || [];
  const steps: SellingGuideStep[] = selectedGuide?.steps || [];
  const currentStep = steps[currentStepIndex] || null;
  const isLastStep = currentStepIndex >= steps.length - 1;

  const handleSelectGuide = useCallback((guideId: number) => {
    setSelectedGuideId(guideId);
    setPhase('answering');
    setCurrentStepIndex(0);
    setAnswers({});
    setSuggestions(null);
  }, []);

  const handleAnswer = useCallback(
    (field: string, value: string) => {
      const newAnswers = { ...answers, [field]: value };
      setAnswers(newAnswers);
      evaluateMutation.mutate(newAnswers);
    },
    [answers, evaluateMutation],
  );

  const handleNextStep = useCallback(() => {
    if (isLastStep) {
      setPhase('results');
    } else {
      setCurrentStepIndex((prev) => prev + 1);
    }
  }, [isLastStep]);

  const handlePrevStep = useCallback(() => {
    if (currentStepIndex > 0) {
      setCurrentStepIndex((prev) => prev - 1);
    } else {
      setPhase('select-guide');
      setSelectedGuideId(null);
    }
  }, [currentStepIndex]);

  const handleComplete = useCallback(() => {
    if (!suggestions) return;
    const items = suggestions.suggested_parts.map((part) => ({
      spare_part_id: part.id,
      honeywell_code: part.honeywell_code,
      description: part.name,
      quantity: 1,
      unit_price: part.unit_price,
      discount_pct: 0,
    }));
    onComplete(items);
    toast.success(t('quotes.guided_added_to_quote').replace('{count}', String(items.length)));
    onClose();
  }, [suggestions, onComplete, onClose, t]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-4xl rounded-xl bg-white shadow-2xl max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-gray-900">{t('quotes.guided_title')}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 transition-colors"
            aria-label={t('quotes.guided_close')}
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-6">
          {phase === 'select-guide' && (
            <div className="space-y-4">
              <p className="text-sm text-gray-600">{t('quotes.guided_pick')}</p>
              {isLoadingGuides && (
                <div className="py-8 text-center text-sm text-gray-400">
                  {t('quotes.guided_loading')}
                </div>
              )}
              {!isLoadingGuides && guides.length === 0 && (
                <div className="py-8 text-center text-sm text-gray-400">
                  {t('quotes.guided_no_guides')}
                </div>
              )}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {guides.map((guide) => (
                  <button
                    key={guide.id}
                    type="button"
                    onClick={() => handleSelectGuide(guide.id)}
                    className="rounded-lg border border-gray-200 p-4 text-left hover:border-honeywell-red hover:bg-honeywell-red/5 transition-colors"
                  >
                    <h3 className="font-medium text-gray-900">{guide.name}</h3>
                    {guide.description && (
                      <p className="mt-1 text-sm text-gray-500">{guide.description}</p>
                    )}
                    <span className="mt-2 inline-block text-xs text-gray-400">
                      {guide.steps.length}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {phase === 'answering' && (
            <div className="flex gap-6">
              {/* Left: Question */}
              <div className="flex-1 space-y-4">
                {/* Progress */}
                <div className="flex items-center gap-2 text-xs text-gray-400">
                  <span>
                    {tx(t('quotes.guided_step_of'), {
                      step: currentStepIndex + 1,
                      total: steps.length,
                    })}
                  </span>
                  <div className="flex-1 h-1.5 rounded-full bg-gray-100">
                    <div
                      className="h-1.5 rounded-full bg-honeywell-red transition-all"
                      style={{ width: `${((currentStepIndex + 1) / steps.length) * 100}%` }}
                    />
                  </div>
                </div>

                {currentStep && (
                  <Card title={currentStep.question}>
                    <div className="space-y-2">
                      {currentStep.options.map((option) => {
                        const isSelected = answers[currentStep.field] === option;
                        return (
                          <label
                            key={option}
                            className={`flex cursor-pointer items-center gap-3 rounded-lg border p-3 transition-colors ${
                              isSelected
                                ? 'border-honeywell-red bg-honeywell-red/5'
                                : 'border-gray-200 hover:bg-gray-50'
                            }`}
                          >
                            <input
                              type="radio"
                              name={currentStep.field}
                              value={option}
                              checked={isSelected}
                              onChange={() => handleAnswer(currentStep.field, option)}
                              className="h-4 w-4 text-honeywell-red accent-honeywell-red"
                            />
                            <span className="text-sm text-gray-900">{option}</span>
                          </label>
                        );
                      })}
                    </div>
                  </Card>
                )}

                <div className="flex gap-2">
                  <Button variant="secondary" onClick={handlePrevStep}>
                    {t('quotes.guided_back')}
                  </Button>
                  <Button
                    onClick={handleNextStep}
                    disabled={!currentStep || !answers[currentStep.field]}
                  >
                    {isLastStep ? t('quotes.guided_see_results') : t('quotes.guided_next')}
                  </Button>
                </div>
              </div>

              {/* Right: Live suggestions */}
              <div className="w-72 shrink-0 space-y-3">
                <h4 className="text-sm font-semibold text-gray-700">
                  {t('quotes.guided_suggested_products')}
                </h4>
                {evaluateMutation.isPending && (
                  <p className="text-xs text-gray-400">{t('quotes.guided_loading')}</p>
                )}
                {suggestions &&
                  suggestions.suggested_parts.length === 0 &&
                  suggestions.suggested_bundles.length === 0 && (
                    <p className="text-xs text-gray-400">{t('quotes.guided_no_suggestions')}</p>
                  )}
                {suggestions?.suggested_parts.map((part) => (
                  <div key={part.id} className="rounded-lg border border-gray-100 bg-gray-50 p-3">
                    <p className="text-xs font-mono font-semibold text-gray-700">
                      {part.honeywell_code}
                    </p>
                    <p className="text-xs text-gray-500">{part.name}</p>
                    <p className="mt-1 text-xs font-medium text-gray-900">
                      {formatCurrency(part.unit_price, 'TRY')}
                    </p>
                  </div>
                ))}
                {suggestions?.suggested_bundles.map((bundle) => (
                  <div key={bundle.id} className="rounded-lg border border-blue-100 bg-blue-50 p-3">
                    <p className="text-xs font-semibold text-blue-700">{bundle.name}</p>
                    {bundle.description && (
                      <p className="text-xs text-blue-500">{bundle.description}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {phase === 'results' && (
            <div className="space-y-4">
              <h3 className="text-base font-semibold text-gray-900">
                {t('quotes.guided_results')}
              </h3>
              <p className="text-sm text-gray-500">
                {t('quotes.guided_match_line').replace(
                  '{count}',
                  String(suggestions?.match_count || 0),
                )}
              </p>

              {suggestions && suggestions.suggested_parts.length > 0 && (
                <Card title={t('quotes.guided_suggested_parts')}>
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 bg-gray-50">
                        <th className="px-3 py-2 text-xs font-semibold text-gray-500">Kod</th>
                        <th className="px-3 py-2 text-xs font-semibold text-gray-500">
                          {t('quotes.guided_desc')}
                        </th>
                        <th className="px-3 py-2 text-xs font-semibold text-gray-500 text-right">
                          {t('quotes.editor_col_unit_price')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {suggestions.suggested_parts.map((part) => (
                        <tr key={part.id} className="border-b border-gray-100">
                          <td className="px-3 py-2 font-mono text-xs">{part.honeywell_code}</td>
                          <td className="px-3 py-2 text-sm text-gray-700">{part.name}</td>
                          <td className="px-3 py-2 text-right text-sm font-medium">
                            {formatCurrency(part.unit_price, 'TRY')}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </Card>
              )}

              {suggestions && suggestions.suggested_bundles.length > 0 && (
                <Card title={t('quotes.guided_suggested_bundles')}>
                  <div className="space-y-2">
                    {suggestions.suggested_bundles.map((bundle) => (
                      <div
                        key={bundle.id}
                        className="rounded-lg border border-blue-100 bg-blue-50 p-3"
                      >
                        <p className="font-medium text-blue-800">{bundle.name}</p>
                        {bundle.description && (
                          <p className="text-sm text-blue-600">{bundle.description}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </Card>
              )}

              <div className="flex gap-2 pt-2">
                <Button variant="secondary" onClick={() => setPhase('answering')}>
                  {t('common.back')}
                </Button>
                <Button
                  onClick={handleComplete}
                  disabled={!suggestions || suggestions.suggested_parts.length === 0}
                >
                  {t('quotes.guided_create_quote')}
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
