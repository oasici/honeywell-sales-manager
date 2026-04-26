import { Plus, Trash2 } from 'lucide-react';

import type { TriggerCondition } from '../../lib/types';

const FIELD_OPTIONS = [
  { value: 'signal_type', label: 'Sinyal Tipi' },
  { value: 'severity', label: 'Siddet' },
  { value: 'stage', label: 'Aşama' },
  { value: 'amount', label: 'Tutar' },
  { value: 'priority', label: 'Oncelik' },
  { value: 'source_entity_type', label: 'Kaynak Varlık Tipi' },
];

const OPERATOR_OPTIONS = [
  { value: 'eq', label: 'Esit' },
  { value: 'neq', label: 'Esit Değil' },
  { value: 'gte', label: '>=' },
  { value: 'lte', label: '<=' },
  { value: 'contains', label: 'İçerir' },
  { value: 'in', label: 'Listede' },
];

interface ConditionBuilderProps {
  conditions: TriggerCondition[];
  onChange: (conditions: TriggerCondition[]) => void;
  readOnly?: boolean;
}

const SELECT_CLASS =
  'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white';

const INPUT_CLASS =
  'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-800 dark:text-white';

function getFieldLabel(value: string): string {
  return FIELD_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

function getOperatorLabel(value: string): string {
  return OPERATOR_OPTIONS.find((o) => o.value === value)?.label ?? value;
}

export function ConditionBuilder({ conditions, onChange, readOnly }: ConditionBuilderProps) {
  const handleAdd = () => {
    onChange([...conditions, { field: 'signal_type', operator: 'eq', value: '' }]);
  };

  const handleRemove = (index: number) => {
    onChange(conditions.filter((_, i) => i !== index));
  };

  const handleUpdate = (index: number, patch: Partial<TriggerCondition>) => {
    onChange(conditions.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  };

  if (readOnly) {
    if (conditions.length === 0) {
      return <p className="text-sm text-slate-500">Tanimlanmis kosul bulunmuyor.</p>;
    }

    return (
      <div className="flex flex-wrap gap-2">
        {conditions.map((c, index) => (
          <span
            key={index}
            className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-300"
          >
            <span className="font-medium">{getFieldLabel(c.field)}</span>
            <span className="text-slate-500 dark:text-slate-400">{getOperatorLabel(c.operator)}</span>
            <span>{c.value}</span>
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {conditions.map((condition, index) => (
        <div key={index} className="flex items-center gap-2">
          <select
            className={SELECT_CLASS}
            value={condition.field}
            onChange={(e) => handleUpdate(index, { field: e.target.value })}
          >
            {FIELD_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          <select
            className={SELECT_CLASS}
            value={condition.operator}
            onChange={(e) => handleUpdate(index, { operator: e.target.value })}
          >
            {OPERATOR_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>

          <input
            type="text"
            className={INPUT_CLASS}
            value={condition.value}
            placeholder="Değer"
            onChange={(e) => handleUpdate(index, { value: e.target.value })}
          />

          <button
            type="button"
            onClick={() => handleRemove(index)}
            className="shrink-0 rounded-lg p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20"
            aria-label="Kosulu sil"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      ))}

      <button
        type="button"
        onClick={handleAdd}
        className="inline-flex items-center gap-1 rounded-lg border border-dashed border-slate-200 px-3 py-2 text-sm text-slate-600 hover:border-slate-300 hover:text-slate-800 dark:border-slate-700 dark:text-slate-400 dark:hover:border-gray-500 dark:hover:text-slate-300"
      >
        <Plus className="h-4 w-4" />
        Kosul Ekle
      </button>
    </div>
  );
}
