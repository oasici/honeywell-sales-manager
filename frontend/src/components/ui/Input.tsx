import { forwardRef, useId, type InputHTMLAttributes } from 'react';

/**
 * Input — single-line text field with label, error, helper.
 *
 * Design notes:
 *   - 44px height (h-11) — touch-friendly, matches Button lg
 *   - 12px radius — same family as Button md/lg
 *   - 3px ring on focus (Linear/Stripe pattern); never shifts layout
 *   - error overrides focus color to red so the affordance is immediate
 *   - label: 13px / 500 / mb-1.5; helper + error: 12px below the field
 */
interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, helperText, className = '', id, ...rest }, ref) => {
    const generatedId = useId();
    const inputId = id || generatedId;
    const errorId = error ? `${inputId}-error` : undefined;
    const helperId = helperText ? `${inputId}-helper` : undefined;
    const describedBy = [errorId, helperId].filter(Boolean).join(' ') || undefined;

    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={inputId}
            className="mb-1.5 block text-[13px] font-medium text-slate-700 dark:text-slate-300"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={[
            'block w-full h-11 px-3.5 text-sm',
            'rounded-[12px] border bg-white',
            'text-slate-900 placeholder:text-slate-400',
            'transition-[border-color,box-shadow] duration-150',
            'focus:outline-none focus:ring-[3px]',
            'dark:bg-transparent dark:text-slate-100 dark:placeholder:text-slate-500',
            'disabled:bg-slate-50 disabled:text-slate-400 disabled:cursor-not-allowed',
            'dark:disabled:bg-slate-800/50',
            error
              ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
              : 'border-slate-200 focus:border-honeywell-red focus:ring-honeywell-red/20 dark:border-slate-700',
            className,
          ].join(' ')}
          {...rest}
        />
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

Input.displayName = 'Input';
