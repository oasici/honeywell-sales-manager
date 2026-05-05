import { QueryClient } from '@tanstack/react-query';

/**
 * Shared QueryClient — extracted from main.tsx so non-component code
 * (auth store, axios interceptors) can call queryClient.clear() on
 * logout / 401 to prevent PII flash on shared devices (R5-CACHE-1).
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
});
