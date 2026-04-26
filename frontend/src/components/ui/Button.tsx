import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { LoadingSpinner } from './LoadingSpinner';

/**
 * Button — Linear/Stripe-style hierarchy.
 *
 * Variants:
 *   primary     filled brand red, single most-prominent action per view
 *   secondary   outline on white surface, neutral confirm/cancel pair
 *   tertiary    text-only, low-emphasis inline actions ("Daha fazla", "İptal")
 *   danger      destructive (delete, revoke); same visual weight as primary
 *   ghost       hover-only background; for icon buttons + table row actions
 *
 * Sizes (heights match input field heights for form alignment):
 *   sm  h-8  (32px)   compact tables / inline filters
 *   md  h-10 (40px)   default — cards, forms
 *   lg  h-11 (44px)   primary CTAs, hero forms, mobile-friendly
 *
 * All variants share: 12px radius, 3px focus ring, 150ms transitions, active scale.
 */
export type ButtonVariant = 'primary' | 'secondary' | 'tertiary' | 'danger' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  children: ReactNode;
}

const variantClasses: Record<ButtonVariant, string> = {
  primary: [
    'bg-honeywell-red text-white shadow-xs',
    'hover:bg-honeywell-dark hover:shadow-sm',
    'active:bg-honeywell-dark',
  ].join(' '),
  secondary: [
    'bg-white text-slate-700 border border-slate-200 shadow-xs',
    'hover:bg-slate-50 hover:border-slate-300',
    'active:bg-slate-100',
    'dark:bg-transparent dark:text-slate-200 dark:border-slate-700',
    'dark:hover:bg-white/5 dark:hover:border-slate-600',
  ].join(' '),
  tertiary: [
    'bg-transparent text-slate-700 border border-transparent',
    'hover:bg-slate-100 hover:text-slate-900',
    'active:bg-slate-200',
    'dark:text-slate-300 dark:hover:bg-white/5 dark:hover:text-slate-100',
  ].join(' '),
  danger: [
    'bg-red-600 text-white shadow-xs',
    'hover:bg-red-700 hover:shadow-sm',
    'active:bg-red-800',
  ].join(' '),
  ghost: [
    'bg-transparent text-slate-500',
    'hover:bg-slate-100 hover:text-slate-700',
    'active:bg-slate-200',
    'dark:text-slate-400 dark:hover:bg-white/5 dark:hover:text-slate-200',
  ].join(' '),
};

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5 rounded-[10px]',
  md: 'h-10 px-4 text-sm gap-2 rounded-[12px]',
  lg: 'h-11 px-5 text-sm gap-2 rounded-[12px]',
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
        className={[
          'inline-flex items-center justify-center font-medium whitespace-nowrap',
          'cursor-pointer select-none',
          'transition-[background-color,border-color,color,box-shadow,transform]',
          'duration-150 ease-out',
          'focus-visible:outline-none focus-visible:ring-[3px]',
          'focus-visible:ring-honeywell-red/20',
          'active:scale-[0.98]',
          'disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100',
          variantClasses[variant],
          sizeClasses[size],
          className,
        ].join(' ')}
        {...rest}
      >
        {loading && <LoadingSpinner size="sm" />}
        {children}
      </button>
    );
  },
);

Button.displayName = 'Button';
