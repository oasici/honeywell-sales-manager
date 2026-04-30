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
  const { data, isSuccess } = useQuery<FeatureFlagsResponse>({
    queryKey: ['config', 'feature-flags'],
    queryFn: () => configApi.getFeatureFlags(),
    // Flags don't change at runtime in practice — Render redeploys
    // when env vars change. 5min stale time covers manual reloads.
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: false,
    // Auth-gated endpoint; the AuthGuard component already prevents
    // rendering before login, so this query won't fire pre-login.
    retry: 1,
  });

  const value = useMemo<FeatureFlagContextValue>(() => {
    if (!data) return FALLBACK_VALUE;
    return {
      flags: data.flags,
      env: data.env,
      release: data.release,
      isLoaded: isSuccess,
      isEnabled: (flag: string) => Boolean(data.flags[flag]),
    };
  }, [data, isSuccess]);

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
