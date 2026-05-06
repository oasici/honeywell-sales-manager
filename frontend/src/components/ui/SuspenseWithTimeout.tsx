import { Suspense, useEffect, useState, type ReactNode } from 'react';
import { LoadingSpinner } from './LoadingSpinner';

interface TimeoutFallbackProps {
  timeoutMs?: number;
}

/**
 * Shown inside a Suspense boundary. Renders a LoadingSpinner initially, then
 * after `timeoutMs` switches to a helpful "still loading..." card with a
 * "Yeniden yukle" button. This prevents the "sonsuz yukleme" UX when a lazy
 * chunk fails or a sync component blocks for too long.
 */
function TimeoutFallback({ timeoutMs = 5000 }: TimeoutFallbackProps) {
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    const id = window.setTimeout(() => setTimedOut(true), timeoutMs);
    return () => window.clearTimeout(id);
  }, [timeoutMs]);

  if (!timedOut) {
    return <LoadingSpinner />;
  }

  return (
    <div className="flex min-h-[400px] flex-col items-center justify-center px-4 text-center">
      <div className="mb-4 h-12 w-12 animate-spin rounded-full border-4 border-slate-200 border-t-honeywell-red" />
      <h2 className="mb-2 text-lg font-semibold text-slate-900 dark:text-white">
        Sayfa yuklenemedi
      </h2>
      <p className="mb-4 max-w-md text-sm text-slate-500">
        Sayfa beklenenden uzun surede yükleniyor. Baglantinizi kontrol edip sayfayi yeniden
        yukleyin.
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-lg bg-honeywell-red px-4 py-2 text-sm font-medium text-white hover:bg-red-700 transition-colors"
        >
          Sayfayi Yeniden Yükle
        </button>
        <button
          type="button"
          onClick={() => {
            localStorage.removeItem('token');
            localStorage.removeItem('refreshToken');
            // R6-CACHE-1 — see LoadingSpinner.tsx for rationale.
            import('../../lib/queryClient').then((m) => m.queryClient.clear()).catch(() => {});
            window.location.href = '/login';
          }}
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
        >
          Tekrar Giris Yap
        </button>
      </div>
    </div>
  );
}

interface SuspenseWithTimeoutProps {
  children: ReactNode;
  timeoutMs?: number;
}

export function SuspenseWithTimeout({ children, timeoutMs = 5000 }: SuspenseWithTimeoutProps) {
  return <Suspense fallback={<TimeoutFallback timeoutMs={timeoutMs} />}>{children}</Suspense>;
}
