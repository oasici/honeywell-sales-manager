import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { LoadingSpinner } from './LoadingSpinner';

export type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: ReactNode;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    'bg-honeywell-red hover:bg-honeywell-dark text-white shadow-sm hover:shadow-md active:scale-[0.98]',
  secondary:
    'bg-white dark:bg-transparent hover:bg-gray-50 dark:hover:bg-white/5 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-600 hover:border-gray-300 shadow-sm active:scale-[0.98]',
  danger: 'bg-red-600 hover:bg-red-700 text-white shadow-sm active:scale-[0.98]',
  ghost:
    'hover:bg-gray-100 dark:hover:bg-white/5 text-gray-600 dark:text-gray-400 active:scale-[0.98]',
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-sm rounded-md',
  md: 'px-4 py-2 text-sm rounded-lg',
  lg: 'px-6 py-3 text-base rounded-lg',
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      loading = false,
      disabled,
      children,
      className = '',
      type = 'button',
      ...rest
    },
    ref,
  ) => {
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        type={type}
        disabled={isDisabled}
        className={`inline-flex items-center justify-center gap-2 font-semibold cursor-pointer
          transition-all duration-200
          focus-visible:ring-2 focus-visible:ring-honeywell-red/50 focus-visible:ring-offset-2 focus-visible:outline-none
          disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100
          ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
        {...rest}
      >
        {loading && <LoadingSpinner size="sm" />}
        {children}
      </button>
    );
  },
);

Button.displayName = 'Button';
