import { forwardRef, useId, type InputHTMLAttributes } from 'react';

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
            className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className={`block w-full rounded-lg border px-3 py-2 text-sm
            transition-colors duration-200
            placeholder:text-gray-400 dark:placeholder:text-gray-500
            bg-white dark:bg-transparent
            text-gray-900 dark:text-gray-100
            focus:outline-none focus:ring-2 focus:ring-offset-0
            ${
              error
                ? 'border-red-500 focus:border-red-500 focus:ring-red-200 dark:focus:ring-red-900/30'
                : 'border-gray-300 dark:border-gray-600 focus:border-honeywell-red focus:ring-honeywell-light dark:focus:ring-honeywell-red/20'
            }
            disabled:bg-gray-50 disabled:text-gray-500 dark:disabled:bg-gray-800
            ${className}`}
          {...rest}
        />
        {error && (
          <p id={errorId} className="mt-1 text-xs text-red-600 dark:text-red-400" role="alert">
            {error}
          </p>
        )}
        {helperText && (
          <p
            id={helperId}
            className={`mt-1 text-xs ${error ? 'text-gray-400 dark:text-gray-500' : 'text-gray-500 dark:text-gray-400'}`}
          >
            {helperText}
          </p>
        )}
      </div>
    );
  },
);

Input.displayName = 'Input';
