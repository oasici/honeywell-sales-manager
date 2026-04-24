import * as Sentry from '@sentry/react';

/**
 * Initialize Sentry for the React SPA.
 *
 * Safe no-op when VITE_SENTRY_DSN is empty (local dev by default). Called
 * once from main.tsx *before* createRoot so the SDK instruments router
 * and fetch from the first render.
 *
 * Session Replay is sampled at 0% under normal operation but 100% for
 * sessions that hit an error — we get debug context for real failures
 * without shipping video of every user.
 */
export function initSentry(): void {
  const dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
  if (!dsn) {
    return;
  }

  const env = (import.meta.env.VITE_ENV as string | undefined) ?? 'development';
  const release = (import.meta.env.VITE_GIT_COMMIT as string | undefined) ?? 'dev';
  const isProdLike = env === 'production' || env === 'sandbox';

  Sentry.init({
    dsn,
    environment: env,
    release,
    // Same-origin tunnel — Turkish ISPs + corporate AV + ad blockers all
    // reset direct *.sentry.io connections. Routing through our backend
    // keeps the request indistinguishable from any other API call.
    tunnel: '/api/sentry-tunnel',
    integrations: [
      Sentry.browserTracingIntegration(),
      Sentry.replayIntegration({
        maskAllText: true,
        blockAllMedia: true,
      }),
    ],
    // Performance traces: 10% in prod-like envs, 100% locally.
    tracesSampleRate: isProdLike ? 0.1 : 1.0,
    // Session replay: only capture when an error fires.
    replaysSessionSampleRate: 0.0,
    replaysOnErrorSampleRate: 1.0,
    // Don't bother upstream with URL health checks.
    tracePropagationTargets: ['localhost', /^\/api\/v1\//],
    // Client-side scrub for request bodies (backend does its own too).
    sendDefaultPii: false,
  });
}

export { Sentry };
