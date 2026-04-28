import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { sentryVitePlugin } from '@sentry/vite-plugin';

/**
 * Vite config.
 *
 * Sentry source map upload + release tracking is wired in conditionally:
 * the plugin only does network work when SENTRY_AUTH_TOKEN is present
 * (i.e. CI / Render builds), so local `npm run build` stays offline-safe.
 *
 * Release naming
 * --------------
 * Sentry needs a stable release identifier that matches what the SDK
 * reports at runtime. We use the commit SHA in this priority:
 *   1. SENTRY_RELEASE   — explicit override (CI/CD pipelines)
 *   2. VITE_GIT_COMMIT  — already set by render.yaml; also exposed to
 *                         the SDK via initSentry() so reporter and
 *                         uploader agree on the same name
 *   3. RENDER_GIT_COMMIT — Render injects this automatically
 *   4. fallback "dev"   — should not happen in CI
 *
 * Source maps are emitted in production builds so traces de-minify in
 * the Sentry UI; they're then uploaded by the plugin and (optionally)
 * deleted from `dist/` afterwards via `sourcemaps.filesToDeleteAfterUpload`
 * to avoid shipping them to end users.
 */
const sentryAuthToken = process.env.SENTRY_AUTH_TOKEN;
const sentryRelease =
  process.env.SENTRY_RELEASE ||
  process.env.VITE_GIT_COMMIT ||
  process.env.RENDER_GIT_COMMIT ||
  undefined;

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Only register the Sentry plugin when an auth token is available.
    // The plugin is itself a no-op without one, but skipping registration
    // keeps the build log quiet on local dev and PR previews.
    ...(sentryAuthToken
      ? [
          sentryVitePlugin({
            org: process.env.SENTRY_ORG || 'onur-asc',
            project: process.env.SENTRY_PROJECT || 'honeywell-frontend',
            authToken: sentryAuthToken,
            release: sentryRelease ? { name: sentryRelease } : undefined,
            sourcemaps: {
              // Upload all JS chunks emitted by Vite, then strip the
              // `.map` files from `dist/` so they aren't served to the
              // public. Sentry keeps its own copy.
              assets: ['./dist/**/*.js', './dist/**/*.js.map'],
              filesToDeleteAfterUpload: ['./dist/**/*.js.map'],
            },
            telemetry: false,
          }),
        ]
      : []),
  ],
  build: {
    // Required for Sentry to be able to symbolicate stack traces. The
    // plugin uploads these during `npm run build` and `filesToDeleteAfterUpload`
    // strips them locally so no maps are served to end users.
    sourcemap: true,
    // Manual vendor chunks so the main app bundle doesn't pull every
    // dependency on first load. Without this Rollup co-locates anything
    // imported from the App.tsx module graph (sentry/react, recharts,
    // react-query) into ``index-*.js``, which crosses 700 kB. Splitting
    // the heaviest libs into named chunks lets the browser cache them
    // across deploys (only the ``index-*.js`` hash changes on a code
    // edit) and reduces the warm-cache JS payload.
    rollupOptions: {
      output: {
        // Manual vendor chunking. Rolldown-vite's typings only accept
        // the function form, so we route the heaviest deps to named
        // chunks based on the resolved id substring. Anything not
        // matched falls back to the default heuristic.
        manualChunks: (id: string) => {
          if (id.includes('node_modules/recharts')) return 'recharts';
          if (id.includes('node_modules/@sentry')) return 'sentry';
          if (id.includes('node_modules/@tanstack/react-query')) {
            return 'react-query';
          }
          return undefined;
        },
      },
    },
  },
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
});
