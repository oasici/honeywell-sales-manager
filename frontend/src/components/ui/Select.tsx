import { forwardRef, useId, type SelectHTMLAttributes } from 'react';
import { ChevronDown } from 'lucide-react';

/**
 * Select — design-system dropdown that mirrors Input.
 *
 * Visual:
 *   - 44px height (h-11), 12px radius — same family as Input lg.
 *   - Right-side ChevronDown chip (we hide the native arrow with appearance-none)
 *     so the affordance stays consistent across browsers.
 *   - 3px brand-tinted focus ring; never shifts layout.
 *   - error overrides border + ring to red so the affordance is immediate.
 *   - label: 13/500 with mb-1.5; error: 12/500 below the field.
 */
interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  helperText?: string;
  options: SelectOption[];
  placeholder?: string;
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(
  (
    { label, error, helperText, options, placeholder, className = '', id, ...rest },
    ref,
  ) => {
    const generatedId = useId();
    const selectId = id || generatedId;
    const errorId = error ? `${selectId}-error` : undefined;
    const helperId = helperText ? `${selectId}-helper` : undefined;
    const describedBy = [errorId, helperId].filter(Boolean).join(' ') || undefined;

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={selectId}
            className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300"
          >
            {label}
          </label>
        )}
        <div className="relative">
          <select
            ref={ref}
            id={selectId}
            aria-invalid={error ? true : undefined}
            aria-describedby={describedBy}
            className={[
              'block w-full h-11 pl-3.5 pr-10 text-sm appearance-none',
              'rounded-[12px] border bg-white',
              'text-slate-900',
              'transition-[border-color,box-shadow] duration-150',
              'focus:outline-none focus:ring-[3px]',
              'dark:bg-transparent dark:text-slate-100',
              'disabled:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed',
              'dark:disabled:bg-slate-800/50',
              error
                ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
                : 'border-slate-200 focus:border-honeywell-red focus:ring-honeywell-red/20 dark:border-slate-700',
              className,
            ].join(' ')}
            {...rest}
          >
            {placeholder && (
              <option value="" disabled>
                {placeholder}
              </option>
            )}
            {options.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <ChevronDown
            size={16}
            className="pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400"
            aria-hidden
          />
        </div>
        {error && (
          <p
            id={errorId}
            className="mt-1.5 text-xs font-medium text-red-600 dark:text-red-400"
            role="alert"
          >
            {error}
          </p>
        )}
        {helperText && !error && (
          <p id={helperId} className="mt-1.5 text-xs text-slate-500 dark:text-slate-400">
            {helperText}
          </p>
        )}
      </div>
    );
  },
);

Select.displayName = 'Select';
