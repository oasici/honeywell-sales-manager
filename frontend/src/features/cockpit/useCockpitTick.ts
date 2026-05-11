import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

/**
 * Round-10 R10-SSE-1 — single-source-of-truth cockpit refresh tick.
 *
 * CockpitPage used to fire 16 independent `refetchInterval` timers
 * (30 s + 60 s ×5 + 120 s ×9 + 300 s ×1). One open tab produced
 * ~57 backend requests every 5 min and 16 wakeups/minute, all on
 * independent clocks.
 *
 * This hook subscribes to the backend SSE stream at
 * `/api/v1/cockpit/stream` and invalidates the cockpit query
 * namespace once per `tick`. Falls back to a single `setInterval`
 * if SSE is unavailable (older proxies / corporate networks).
 *
 * Replaces every `refetchInterval` in CockpitPage; consumers keep
 * their `useQuery` declarations as-is, just drop the interval and
 * let TanStack refetch when the query key invalidates.
 */
export function useCockpitTick() {
  const qc = useQueryClient();

  useEffect(() => {
    // Cookie auth flows through automatically; no Authorization header
    // required because `/api/v1/cockpit/stream` is gated by the same
    // get_current_user dependency that signs every other API call.
    let es: EventSource | null = null;
    let fallback: ReturnType<typeof setInterval> | null = null;

    const invalidate = () => {
      qc.invalidateQueries({ queryKey: ['cockpit'] });
    };

    try {
      es = new EventSource('/api/v1/cockpit/stream', { withCredentials: true });
      es.addEventListener('tick', invalidate);
      es.addEventListener('error', () => {
        // Network blip — fall back to polling so the panel still refreshes.
        if (!fallback) {
          fallback = setInterval(invalidate, 60_000);
        }
      });
    } catch {
      // EventSource not available (very old browsers / SSR) — direct fallback.
      fallback = setInterval(invalidate, 60_000);
    }

    return () => {
      if (es) {
        es.close();
        es = null;
      }
      if (fallback) {
        clearInterval(fallback);
        fallback = null;
      }
    };
  }, [qc]);
}
