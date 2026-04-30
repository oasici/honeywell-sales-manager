import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { initSentry } from './lib/sentry';
import { FeatureFlagProvider } from './contexts/FeatureFlagContext';
import App from './app/App';
import './index.css';

// Initialize before createRoot so the SDK instruments from first render.
initSentry();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <QueryClientProvider client={queryClient}>
          {/* FeatureFlagProvider wraps the whole app so any route or
              sidebar entry can call useFeatureFlag() without prop-
              drilling. The provider itself delays nothing — pages can
              render placeholders while the flags fetch lands. */}
          <FeatureFlagProvider>
            <App />
          </FeatureFlagProvider>
          {/* Toast styling tuned to design system: 12px radius, slate-200
              border, --shadow-lg elevation, white surface (light) / slate-900
              (dark). richColors keeps the colored variants (success/error/
              warning/info) but they inherit our token border + shadow. */}
          <Toaster
            position="top-right"
            richColors
            closeButton
            duration={4500}
            offset={20}
            toastOptions={{
              style: {
                borderRadius: '12px',
                border: '1px solid var(--border)',
                boxShadow: 'var(--shadow-lg)',
                background: 'var(--surface)',
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-sans)',
                fontSize: '13px',
                fontWeight: 500,
                padding: '12px 14px',
              },
              className: 'sonner-toast-modern',
            }}
          />
        </QueryClientProvider>
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
);

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}
