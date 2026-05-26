/**
 * FeatureFlagContext
 *
 * Single source of truth for which backend feature flags are on for
 * the running deployment. Resolves on app boot via
 * ``GET /config/feature-flags`` and exposes:
 *
 *   - ``isEnabled(flag)`` → boolean lookup
 *   - ``flags`` → raw map for advanced consumers
 *   - ``env`` → "development" | "staging" | "production"
 *   - ``release`` → git sha or build tag (for support / Sentry corr.)
 *   - ``isLoaded`` → guard to defer flag-gated rendering until the
 *     fetch lands; treating "not yet loaded" as "off" was producing
 *     empty pages on first paint
 *
 * The audit (#5.4) flagged that the frontend hard-coded routes which
 * 404'd when their backing flag was off — this context lets routes
 * and sidebar items short-circuit BEFORE making the request, so the
 * UX is "the menu item isn't there" instead of "the page errors".
 */

import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';

import { configApi, type FeatureFlagsResponse } from '../lib/api';

interface FeatureFlagContextValue {
  flags: Record<string, boolean>;
  env: string;
  release: string;
  isLoaded: boolean;
  /**
   * Flag lookup. Returns ``false`` when the flag is unknown OR the
   * backend hasn't responded yet — callers should pair this with
   * ``isLoaded`` if they need to distinguish "off" from "not yet
   * known".
   */
  isEnabled: (flag: string) => boolean;
}

const FeatureFlagContext = createContext<FeatureFlagContextValue | null>(null);

const FALLBACK_VALUE: FeatureFlagContextValue = {
  flags: {},
  env: 'unknown',
  release: 'unknown',
  isLoaded: false,
  isEnabled: () => false,
};

export function FeatureFlagProvider({ children }: { children: ReactNode }) {
  // R14-FE-1 exempt: boot-time flag fetch; SPA falls back to FEATURE_DEFAULTS on error so the app keeps booting
  const { data, isSuccess, isError, error } = useQuery<FeatureFlagsResponse>({
    queryKey: ['config', 'feature-flags'],
    queryFn: () => configApi.getFeatureFlags(),
    // Flags don't change at runtime in practice — Render redeploys
    // when env vars change. 5min stale time covers manual reloads.
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    // Auth-gated endpoint; the AuthGuard component already prevents
    // rendering before login, so this query won't fire pre-login.
    // Three retries because Render Free cold-starts can take 30-60s;
    // a single retry was producing permanent blank pages whenever the
    // backend container had spun down (Round-19 R19-FE-1).
    retry: 3,
    retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 8000),
  });

  const value = useMemo<FeatureFlagContextValue>(() => {
    if (data) {
      return {
        flags: data.flags,
        env: data.env,
        release: data.release,
        isLoaded: isSuccess,
        isEnabled: (flag: string) => Boolean(data.flags[flag]),
      };
    }
    if (isError) {
      // Round-19 R19-FE-1 — fail-open when the flag fetch errors out.
      // Pre-Round-19 the gate hung at `isLoaded=false` and every
      // gated route (Cockpit, Forecast, Parts Intel, Compliance,
      // Contracts, Campaigns, Invoices, Subscriptions, Dashboards,
      // Approvals, Reports Builder, Leads, Workflow Rules, Custom
      // Fields, Territories, Rev Rec — 20+ surfaces) rendered as a
      // permanently blank page on Render after cold-start failures.
      // These flags are UX/discovery gates only — the backend still
      // enforces feature access on every endpoint via `_require_*`
      // dependencies — so fail-open is safe and keeps the SPA usable.
      // The console warn surfaces the underlying error for support.
      console.warn(
        '[FeatureFlagGate] /config/feature-flags failed; falling open. ' +
          'Backend still enforces per-route. Error:',
        error,
      );
      return {
        flags: {},
        env: 'unknown',
        release: 'unknown',
        isLoaded: true,
        isEnabled: () => true,
      };
    }
    return FALLBACK_VALUE;
  }, [data, isSuccess, isError, error]);

  return <FeatureFlagContext.Provider value={value}>{children}</FeatureFlagContext.Provider>;
}

export function useFeatureFlags(): FeatureFlagContextValue {
  // Default to the fallback shape rather than throwing — pages
  // mounted outside the provider (e.g. login) shouldn't crash.
  return useContext(FeatureFlagContext) ?? FALLBACK_VALUE;
}

/**
 * Convenience hook for the most common case: "is flag X on?"
 */
export function useFeatureFlag(flag: string): boolean {
  return useFeatureFlags().isEnabled(flag);
}

/**
 * Round-4 R4-FLAG-1 — gate component. Wrap a route element to refuse
 * rendering when its backing feature flag is off.
 *
 * While the flag map is still loading we render `null` (a brief blank)
 * instead of the fallback, because rendering "Forbidden" and then
 * flipping to the page is worse UX than a 100ms blank flash. Once
 * loaded, missing/false → fallback (default: a friendly 404 panel).
 *
 *   <Route path="/cockpit" element={
 *     <FeatureFlagGate flag="FEATURE_REVENUE_COCKPIT"><CockpitPage/></FeatureFlagGate>
 *   } />
 */
export function FeatureFlagGate({
  flag,
  children,
  fallback,
}: {
  flag: string;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { isEnabled, isLoaded } = useFeatureFlags();
  // Round-19 R19-FE-1 — during the in-flight flag fetch (cold start)
  // render a centred spinner instead of bare `null`. Returning `null`
  // produced a fully blank main pane that was indistinguishable from
  // a crashed route, so support kept getting tickets like "the page
  // doesn't open" for routes that were just waiting on /config.
  if (!isLoaded) {
    return (
      <div className="flex h-full min-h-[40vh] items-center justify-center">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-(--border) border-t-honeywell-red" />
      </div>
    );
  }
  if (!isEnabled(flag)) {
    return (
      <>
        {fallback ?? (
          <div className="mx-auto max-w-lg py-16 text-center">
            <p className="text-lg font-semibold text-slate-700">Bu özellik bu hesap için kapalı.</p>
            <p className="mt-2 text-sm text-slate-500">Yöneticinizden etkinleştirmesini isteyin.</p>
          </div>
        )}
      </>
    );
  }
  return <>{children}</>;
}
