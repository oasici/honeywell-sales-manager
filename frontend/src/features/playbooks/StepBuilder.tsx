import { Plus, Trash2 } from 'lucide-react';

import { Badge } from '../../components/ui/Badge';

import type { PlaybookStepDef } from '../../lib/types';

const ACTION_TYPE_OPTIONS = [
  { value: 'task', label: 'Gorev' },
  { value: 'notification', label: 'Bildirim' },
  { value: 'condition', label: 'Kosul' },
];

const PRIORITY_OPTIONS = [
  { value: 'low', label: 'Düşük' },
  { value: 'normal', label: 'Normal' },
  { value: 'high', label: 'Yüksek' },
  { value: 'urgent', label: 'Acil' },
];

const SELECT_CLASS =
  'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white';

const INPUT_CLASS =
  'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white';

const TEXTAREA_CLASS =
  'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white';

interface StepBuilderProps {
  steps: PlaybookStepDef[];
  onChange: (steps: PlaybookStepDef[]) => void;
  readOnly?: boolean;
}

function getActionLabel(value: string): string {
  return ACTION_TYPE_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

function getPriorityLabel(value: string): string {
  return PRIORITY_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

const PRIORITY_BADGE_VARIANT: Record<string, 'default' | 'info' | 'warning' | 'success' | 'danger'> = {
  low: 'default',
  normal: 'info',
  high: 'warning',
  urgent: 'danger',
};

const DEFAULT_STEP: PlaybookStepDef = {
  action_type: 'task',
  template: '',
  delay_days: 0,
  priority: 'normal',
};

export function StepBuilder({ steps, onChange, readOnly }: StepBuilderProps) {
  const handleAdd = () => {
    onChange([...steps, { ...DEFAULT_STEP }]);
  };

  const handleRemove = (index: number) => {
    onChange(steps.filter((_, i) => i !== index));
  };

  const handleUpdate = (index: number, patch: Partial<PlaybookStepDef>) => {
    onChange(steps.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  };

  if (readOnly) {
    if (steps.length === 0) {
      return <p className="text-sm text-slate-500">Tanimlanmis adım bulunmuyor.</p>;
    }

    return (
      <div className="relative space-y-0">
        {steps.map((step, index) => (
          <div key={index} className="relative flex items-start gap-3 pb-4">
            {/* Connector line */}
            {index < steps.length - 1 && (
              <div className="absolute left-3.5 top-8 h-full w-px border-l-2 border-dashed border-slate-200 dark:border-slate-800" />
            )}

            <span className="relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 text-sm font-bold text-blue-700 dark:bg-blue-900 dark:text-blue-300">
              {index + 1}
            </span>

            <div className="flex-1 rounded-lg border border-slate-100 p-3 dark:border-slate-800">
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="info">{getActionLabel(step.action_type)}</Badge>
                {step.priority && (
                  <Badge variant={PRIORITY_BADGE_VARIANT[step.priority] ?? 'default'}>
                    {getPriorityLabel(step.priority)}
                  </Badge>
                )}
                {step.delay_days != null && step.delay_days > 0 && (
                  <span className="text-xs text-slate-500">{step.delay_days} gun bekleme</span>
                )}
              </div>
              {step.template && (
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{step.template}</p>
              )}
              {step.description && (
                <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{step.description}</p>
              )}
              {step.action_type === 'condition' && (
                <div className="mt-1 flex gap-3 text-xs text-slate-500">
                  {step.if_true_step != null && <span>Dogru ise: Adim {step.if_true_step}</span>}
                  {step.if_false_step != null && <span>Yanlis ise: Adim {step.if_false_step}</span>}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-0">
      {steps.map((step, index) => (
        <div key={index} className="relative flex items-start gap-3 pb-4">
          {/* Connector line */}
          {index < steps.length - 1 && (
            <div className="absolute left-3.5 top-8 h-full w-px border-l-2 border-dashed border-slate-200 dark:border-slate-800" />
          )}

          <span className="relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-600 text-sm font-bold text-white">
            {index + 1}
          </span>

          <div className="flex-1 rounded-lg border border-slate-200 p-4 dark:border-slate-800">
            <div className="flex items-start justify-between">
              <div className="grid flex-1 gap-3 sm:grid-cols-3">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
                    Aksiyon Tipi
                  </label>
                  <select
                    className={SELECT_CLASS}
                    value={step.action_type}
                    onChange={(e) => handleUpdate(index, { action_type: e.target.value })}
                  >
                    {ACTION_TYPE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
                    Bekleme (gun)
                  </label>
                  <input
                    type="number"
                    min={0}
                    className={INPUT_CLASS}
                    value={step.delay_days ?? 0}
                    onChange={(e) => handleUpdate(index, { delay_days: Number(e.target.value) })}
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
                    Oncelik
                  </label>
                  <select
                    className={SELECT_CLASS}
                    value={step.priority ?? 'normal'}
                    onChange={(e) => handleUpdate(index, { priority: e.target.value })}
                  >
                    {PRIORITY_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <button
                type="button"
                onClick={() => handleRemove(index)}
                className="ml-2 shrink-0 rounded-lg p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
                aria-label="Adimi sil"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-3">
              <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
                Mesaj Şablonu
              </label>
              <textarea
                className={TEXTAREA_CLASS}
                rows={2}
                value={step.template ?? ''}
                placeholder="Mesaj sablonunu yazin..."
                onChange={(e) => handleUpdate(index, { template: e.target.value })}
              />
            </div>

            {step.action_type === 'condition' && (
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
                    Dogru ise (Adım No)
                  </label>
                  <input
                    type="number"
                    min={1}
                    className={INPUT_CLASS}
                    value={step.if_true_step ?? ''}
                    onChange={(e) =>
                      handleUpdate(index, {
                        if_true_step: e.target.value ? Number(e.target.value) : undefined,
                      })
                    }
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
                    Yanlis ise (Adım No)
                  </label>
                  <input
                    type="number"
                    min={1}
                    className={INPUT_CLASS}
                    value={step.if_false_step ?? ''}
                    onChange={(e) =>
                      handleUpdate(index, {
                        if_false_step: e.target.value ? Number(e.target.value) : undefined,
                      })
                    }
                  />
                </div>
              </div>
            )}
          </div>
        </div>
      ))}

      <button
        type="button"
        onClick={handleAdd}
        className="inline-flex items-center gap-1 rounded-lg border border-dashed border-slate-200 px-3 py-2 text-sm text-slate-600 hover:border-slate-300 hover:text-slate-800 dark:border-slate-700 dark:text-slate-400 dark:hover:border-gray-500 dark:hover:text-slate-300"
      >
        <Plus className="h-4 w-4" />
        Adım Ekle
      </button>
    </div>
  );
}
