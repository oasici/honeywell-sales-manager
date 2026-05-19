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
 * Round-11 R11-SSE-2 fixes three small SSE bugs:
 *   1. Fallback `setInterval` was never cleared on reconnect, so
 *      a transient network blip would leave both the SSE stream
 *      AND the polling timer running indefinitely (double invalidation,
 *      doubled backend hits).
 *   2. The effect closed over `[qc]` which made it re-open the stream
 *      every time the queryClient context produced a new reference.
 *      Effect now runs once on mount (deps `[]`) because the SSE
 *      identity doesn't depend on qc, only the invalidate target does.
 *   3. The backend emits `event: hello` immediately on connect; the
 *      hook didn't react, leaving the cockpit on stale data for up to
 *      60 s after navigation. Hello now triggers an invalidation too.
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
      // Round-15 audit F-030 — kanban/board read from independent
      // queryKeys, so a concurrent stage move by another user used to
      // sit stale on the kanban for up to ``staleTime: 30_000`` until
      // the next refetch. SSE ticks now invalidate both keys so the
      // kanban is as live as the cockpit panels.
      qc.invalidateQueries({ queryKey: ['board'] });
      qc.invalidateQueries({ queryKey: ['kanban'] });
    };

    const stopFallback = () => {
      if (fallback) {
        clearInterval(fallback);
        fallback = null;
      }
    };

    const startFallback = () => {
      if (!fallback) {
        fallback = setInterval(invalidate, 60_000);
      }
    };

    try {
      es = new EventSource('/api/v1/cockpit/stream', { withCredentials: true });
      // R11-SSE-2 (#3) — `hello` arrives instantly on connect; refresh
      // cockpit immediately rather than waiting up to 60 s for first tick.
      es.addEventListener('hello', invalidate);
      // `open` fires after the EventSource handshake completes — a good
      // place to stop any polling fallback started by a previous error.
      es.addEventListener('open', stopFallback);
      es.addEventListener('tick', invalidate);
      es.addEventListener('error', () => {
        // Network blip — fall back to polling so the panel still refreshes.
        // The polling timer is cleared on reconnect (`open` listener above).
        startFallback();
      });
    } catch {
      // EventSource not available (very old browsers / SSR) — direct fallback.
      startFallback();
    }

    return () => {
      if (es) {
        es.close();
        es = null;
      }
      stopFallback();
    };
    // R11-SSE-2 (#2) — deps intentionally empty: queryClient is a stable
    // root singleton so we don't want context-identity churn to re-open
    // the SSE stream. `invalidate` closes over the captured qc reference.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}
