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

  return (
    <div className="flex min-h-[320px] flex-col items-center justify-center px-4 text-center">
      <div className="mb-4 h-12 w-12 animate-spin rounded-full border-4 border-gray-200 border-t-honeywell-red" />
      <h2 className="mb-1 text-base font-semibold text-gray-900 dark:text-white">
        {t('loading.stuck_title')}
      </h2>
      <p className="mb-4 max-w-md text-xs text-gray-500">{t('loading.stuck_body')}</p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-lg bg-honeywell-red px-4 py-2 text-xs font-medium text-white hover:bg-red-700 transition-colors"
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
          className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors dark:border-gray-600 dark:bg-gray-800 dark:text-gray-200"
        >
          {t('loading.relogin')}
        </button>
      </div>
    </div>
  );
}
