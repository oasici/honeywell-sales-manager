import { useEffect, useState } from 'react';
import { useT } from '../../hooks/useT';

const sizeClasses = {
  sm: 'h-4 w-4',
  md: 'h-8 w-8',
  lg: 'h-12 w-12',
} as const;

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  /**
   * If true, after `timeoutMs` of mounting, shows a "still loading" card
   * with a reload button. Useful as a Suspense fallback so a stuck lazy
   * chunk doesn't leave the user with a spinner forever.
   */
  timeoutEscape?: boolean;
  timeoutMs?: number;
}

function Spinner({ size }: { size: 'sm' | 'md' | 'lg' }) {
  const t = useT();
  return (
    <svg
      className={`animate-spin ${sizeClasses[size]} text-current`}
      xmlns="http://www.w3.org/2000/svg"
      fill="none"
      viewBox="0 0 24 24"
      aria-label={t('common.loading')}
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
      />
    </svg>
  );
}

export function LoadingSpinner({
  size = 'md',
  timeoutEscape,
  timeoutMs = 6000,
}: LoadingSpinnerProps) {
  const t = useT();
  // Only enable timeout escape for md/lg spinners (typical Suspense fallbacks).
  // Small spinners (size="sm") are used inside buttons — never upgrade them.
  const shouldEscape = timeoutEscape ?? size !== 'sm';
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    if (!shouldEscape) return;
    const id = window.setTimeout(() => setTimedOut(true), timeoutMs);
    return () => window.clearTimeout(id);
  }, [shouldEscape, timeoutMs]);

  if (!timedOut) {
    return <Spinner size={size} />;
  }

  // Stuck-state escape: appears after `timeoutMs` so a hung lazy chunk doesn't
  // strand the user with a spinner forever. Uses Button primitives so focus
  // ring and keyboard behavior match the rest of the app.
  return (
    <div className="flex min-h-[320px] flex-col items-center justify-center px-4 text-center">
      <div className="mb-5 h-12 w-12 animate-spin rounded-full border-[3px] border-slate-200 border-t-honeywell-red dark:border-slate-700" />
      <h2 className="text-heading-3 text-slate-900 dark:text-white">
        {t('loading.stuck_title')}
      </h2>
      <p className="mt-1.5 max-w-md text-[13px] text-slate-500 dark:text-slate-400">
        {t('loading.stuck_body')}
      </p>
      <div className="mt-5 flex gap-2">
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="inline-flex h-9 items-center rounded-[12px] bg-honeywell-red px-4 text-[13px] font-semibold text-white transition-colors hover:bg-honeywell-dark focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20"
        >
          {t('loading.reload')}
        </button>
        <button
          type="button"
          onClick={() => {
            localStorage.removeItem('token');
            localStorage.removeItem('refreshToken');
            window.location.href = '/login';
          }}
          className="inline-flex h-9 items-center rounded-[12px] border border-slate-200 bg-white px-4 text-[13px] font-medium text-slate-700 transition-colors hover:bg-slate-50 focus:outline-none focus:ring-[3px] focus:ring-honeywell-red/20 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
        >
          {t('loading.relogin')}
        </button>
      </div>
    </div>
  );
}
