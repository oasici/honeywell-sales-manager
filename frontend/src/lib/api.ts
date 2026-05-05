import axios from 'axios';
import type { AxiosRequestConfig } from 'axios';
import { toast } from 'sonner';
import { tt } from './i18n-runtime';

type ApiRequestConfig = AxiosRequestConfig & { _skipToast?: boolean };
import type {
  TokenResponse,
  User,
  DashboardStats,
  EmailRequest,
  SparePart,
  PriceEntry,
  Customer,
  Quote,
  TopPart,
  TrendData,
  MatchResult,
  PaginatedResponse,
  CustomerHealthReport,
  HealthOverview,
  AtRiskResponse,
  SavedView,
  OpportunityFeaturesDailyLatest,
} from './types';

// ── Axios instance ───────────────────────────────────
// Resolve the API base URL while avoiding cross-origin credentialed requests.
// Browsers reject `Access-Control-Allow-Origin: *` responses when the request
// has `withCredentials: true`. The Render static site already proxies
// `/api/*` to the backend, so when the env URL points to a different origin
// we fall back to the same-origin relative path.
function resolveBackendUrl(): string {
  const envUrl = import.meta.env.VITE_API_URL as string | undefined;
  if (!envUrl) return '/api/v1';
  if (typeof window === 'undefined') return envUrl;
  try {
    const envOrigin = new URL(envUrl, window.location.origin).origin;
    if (envOrigin !== window.location.origin) {
      // Cross-origin env URL — prefer same-origin rewrite to avoid CORS+credentials conflict.
      return '/api/v1';
    }
  } catch {
    /* keep envUrl */
  }
  return envUrl;
}
const BACKEND_URL = resolveBackendUrl();
const COOKIE_AUTH_ONLY = import.meta.env.VITE_COOKIE_AUTH_ONLY === 'true';

const api = axios.create({
  baseURL: BACKEND_URL,
  headers: { 'Content-Type': 'application/json' },
  // Send/receive cookies (HttpOnly access_token + readable csrf_token)
  withCredentials: true,
});

// Read a cookie by name (CSRF cookie is NOT HttpOnly).
function getCookie(name: string): string | null {
  const match = document.cookie.match(
    new RegExp('(^|; )' + name.replace(/[-.]/g, '\\$&') + '=([^;]*)'),
  );
  return match ? decodeURIComponent(match[2]) : null;
}

// Request interceptor — attach Authorization header (backward-compat) AND
// CSRF header for state-changing cookie-auth requests.
api.interceptors.request.use((config) => {
  // Legacy header auth: only if a token exists in localStorage (pre-cookie users)
  const token = COOKIE_AUTH_ONLY ? null : localStorage.getItem('token');
  if (token && !COOKIE_AUTH_ONLY) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  // CSRF: for unsafe methods, echo the cookie value in the X-CSRF-Token header.
  // Backend middleware skips CSRF when Authorization header is present.
  const method = (config.method || 'get').toUpperCase();
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrf = getCookie('csrf_token');
    if (csrf) {
      config.headers['X-CSRF-Token'] = csrf;
    }
  }

  return config;
});

// ── Token refresh queue ─────────────────────────────
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (token) {
      resolve(token);
    } else {
      reject(error);
    }
  });
  failedQueue = [];
};

const clearAuthAndRedirect = () => {
  localStorage.removeItem('token');
  localStorage.removeItem('refreshToken');
  localStorage.removeItem('user');
  // R5-CACHE-1 — wipe TanStack cache on the 401 redirect path so the
  // next user on this browser tab doesn't see prior PII for the
  // 30s staleTime window. Lazy-import to avoid circular dep at boot.
  void import('./queryClient').then((m) => m.queryClient.clear()).catch(() => {});
  // Guard against redirect loop: don't redirect if already on login
  if (!window.location.pathname.startsWith('/login')) {
    window.location.href = '/login';
  }
};

/**
 * Map a backend error code to a Turkish user-facing message.
 *
 * Backend errors are emitted as ``{error: {code, message}}`` (see
 * ``backend/app/core/exceptions.py``). The default toast used to
 * collapse everything into a generic "Beklenmeyen bir hata oluştu",
 * losing the structured signal the API was already sending. This
 * map preserves the operator's intent for the codes we know about
 * and falls through to the raw ``message`` for the rest.
 */
const ERROR_CODE_MESSAGES: Record<string, string> = {
  CSRF_INVALID: 'Oturum doğrulaması başarısız — sayfayı yenileyip tekrar deneyin.',
  NOT_FOUND: 'Aranan kayıt bulunamadı.',
  TENANT_MISMATCH: 'Bu kayda erişim yetkiniz yok (farklı tenant).',
  VALIDATION_ERROR: 'Girilen bilgiler geçerli değil.',
  RATE_LIMITED: 'Çok fazla istek attınız — biraz bekleyip tekrar deneyin.',
  FEATURE_DISABLED: 'Bu özellik şu anda etkin değil.',
  AI_QUOTA_EXCEEDED: 'AI kullanım kotası doldu — yöneticinize başvurun.',
  INTERNAL_ERROR: 'Sunucuda beklenmeyen bir hata oluştu.',
};

/**
 * Build the toast string for an error response. We always append a
 * short request-id reference (first 8 chars of the X-Request-ID
 * header) so support tickets can be correlated to backend logs
 * without asking the user to reproduce. The full id stays in the
 * console for engineers digging into Sentry.
 */
function formatErrorToast(message: string, requestId?: string | null): string {
  if (!requestId) return message;
  const short = requestId.slice(0, 8);
  return `${message} (ref: ${short})`;
}

// Response interceptor – handle errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (!error.response) {
      toast.error('Bağlantı hatası');
      return Promise.reject(error);
    }

    const { status, data, headers } = error.response;
    const originalRequest = error.config;
    // Backend sets X-Request-ID via middleware; surface it so users
    // can copy it into a support ticket. Header names are case-
    // insensitive in HTTP but axios normalises to lowercase, so we
    // try both for safety.
    const requestId: string | null = headers?.['x-request-id'] ?? headers?.['X-Request-ID'] ?? null;
    // Pull the structured error code if the backend sent one.
    const errorCode: string | undefined = data?.error?.code ?? data?.code;
    const errorMessage: string | undefined = data?.error?.message ?? data?.message;

    if (status === 401 && !originalRequest._retry) {
      const refreshToken = COOKIE_AUTH_ONLY ? null : localStorage.getItem('refreshToken');

      if (isRefreshing) {
        return new Promise<string>((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const { data: tokenData } = await axios.post<TokenResponse>(
          `${BACKEND_URL}/auth/refresh`,
          COOKIE_AUTH_ONLY ? {} : { refresh_token: refreshToken },
          { headers: { 'Content-Type': 'application/json' } },
        );

        const newToken = tokenData.access_token;
        if (!COOKIE_AUTH_ONLY) {
          localStorage.setItem('token', newToken);
        }

        if (tokenData.refresh_token) {
          if (!COOKIE_AUTH_ONLY) {
            localStorage.setItem('refreshToken', tokenData.refresh_token);
          }
        }

        processQueue(null, newToken);
        if (!COOKIE_AUTH_ONLY) {
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
        }
        return api(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        clearAuthAndRedirect();
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    } else if (status === 401) {
      clearAuthAndRedirect();
    } else if (originalRequest?._skipToast) {
      // Skip toast for requests that handle errors themselves (e.g. PDF download)
    } else if (status === 403) {
      const codeMessage = errorCode ? ERROR_CODE_MESSAGES[errorCode] : null;
      toast.error(formatErrorToast(codeMessage ?? tt('errors.api_forbidden'), requestId));
    } else if (status === 422) {
      const detail = data?.detail;
      if (Array.isArray(detail)) {
        const messages = detail.map(
          (err: { loc?: string[]; msg?: string }) => err.msg || JSON.stringify(err),
        );
        toast.error(formatErrorToast(messages.join(', '), requestId));
      } else if (typeof detail === 'string') {
        toast.error(formatErrorToast(detail, requestId));
      } else {
        toast.error(formatErrorToast(tt('errors.api_invalid_data'), requestId));
      }
    } else if (status >= 500) {
      // Prefer the backend's structured message + code over the
      // generic fallback when present. Sentry already has the full
      // trace keyed on the same request_id.
      const codeMessage = errorCode ? ERROR_CODE_MESSAGES[errorCode] : null;
      const message = codeMessage ?? errorMessage ?? tt('errors.api_server_error');
      toast.error(formatErrorToast(message, requestId));
    } else if (status >= 400 && errorCode) {
      // Catch-all for 4xx with a structured error code we recognise.
      const codeMessage = ERROR_CODE_MESSAGES[errorCode] ?? errorMessage ?? 'İstek başarısız';
      toast.error(formatErrorToast(codeMessage, requestId));
    }

    return Promise.reject(error);
  },
);

// ── Auth ─────────────────────────────────────────────
export const authApi = {
  login: async (email: string, password: string): Promise<TokenResponse> => {
    const formData = new URLSearchParams();
    formData.append('username', email);
    formData.append('password', password);
    const { data } = await api.post<TokenResponse>('/auth/login', formData, {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    });
    return data;
  },

  getMe: async (): Promise<User> => {
    const { data } = await api.get<User>('/auth/me');
    return data;
  },

  refresh: async (refreshToken?: string | null): Promise<TokenResponse> => {
    const { data } = await api.post<TokenResponse>(
      '/auth/refresh',
      refreshToken ? { refresh_token: refreshToken } : {},
    );
    return data;
  },

  logout: async (refreshToken?: string | null): Promise<void> => {
    await api.post('/auth/logout', refreshToken ? { refresh_token: refreshToken } : {});
  },
};

// ── Dashboard ────────────────────────────────────────
export const dashboardApi = {
  getStats: async (): Promise<DashboardStats> => {
    const { data } = await api.get<DashboardStats>('/dashboard/stats');
    return data;
  },
};

// ── Emails ───────────────────────────────────────────
export const emailsApi = {
  getEmails: async (params?: Record<string, unknown>): Promise<PaginatedResponse<EmailRequest>> => {
    const { data } = await api.get<PaginatedResponse<EmailRequest>>('/emails/', { params });
    return data;
  },

  getEmail: async (id: number): Promise<EmailRequest> => {
    const { data } = await api.get<EmailRequest>(`/emails/${id}`);
    return data;
  },

  createManualEmail: async (payload: Record<string, unknown>): Promise<EmailRequest> => {
    const { data } = await api.post<EmailRequest>('/emails/manual', payload);
    return data;
  },

  pollEmails: async (): Promise<{ message: string }> => {
    const { data } = await api.post<{ message: string }>('/emails/poll');
    return data;
  },

  correctParse: async (
    id: number,
    parsedData: Record<string, unknown>,
  ): Promise<{ message: string; changed_fields: string[] }> => {
    const { data } = await api.patch<{ message: string; changed_fields: string[] }>(
      `/emails/${id}/correct-parse`,
      { parsed_data: parsedData },
    );
    return data;
  },

  reparseEmail: async (id: number): Promise<{ message: string; status: string }> => {
    const { data } = await api.post<{ message: string; status: string }>(`/emails/${id}/reparse`);
    return data;
  },

  markRead: async (id: number): Promise<void> => {
    await api.patch(`/emails/${id}/read`);
  },

  getEmailMatches: async (id: number): Promise<MatchResult[]> => {
    const { data } = await api.get<MatchResult[]>(`/emails/${id}/matches`);
    return data;
  },

  reviewEmail: async (id: number, action: string): Promise<EmailRequest> => {
    const { data } = await api.patch<EmailRequest>(`/emails/${id}/review`, { action });
    return data;
  },

  linkOpportunity: async (
    id: number,
    payload: { opportunity_id: number | null },
  ): Promise<EmailRequest> => {
    const { data } = await api.patch<EmailRequest>(`/emails/${id}/opportunity`, payload);
    return data;
  },
};

// ── Parts ────────────────────────────────────────────
export const partsApi = {
  getParts: async (params?: Record<string, unknown>): Promise<PaginatedResponse<SparePart>> => {
    const { data } = await api.get<PaginatedResponse<SparePart>>('/parts/', { params });
    return data;
  },

  getCategories: async (): Promise<string[]> => {
    // Round-5 Phase 7 — backend now returns the canonical envelope
    // ``{items, total}``. Tolerate the legacy bare-list shape for
    // any in-flight responses mid-deploy.
    const { data } = await api.get<{ items?: string[] } | string[]>(
      '/parts/categories',
    );
    if (Array.isArray(data)) {
      return data;
    }
    return data?.items ?? [];
  },

  getPart: async (id: number): Promise<SparePart> => {
    const { data } = await api.get<SparePart>(`/parts/${id}`);
    return data;
  },

  createPart: async (payload: Partial<SparePart>): Promise<SparePart> => {
    const { data } = await api.post<SparePart>('/parts/', payload);
    return data;
  },

  updatePart: async (id: number, payload: Partial<SparePart>): Promise<SparePart> => {
    const { data } = await api.put<SparePart>(`/parts/${id}`, payload);
    return data;
  },

  deletePart: async (id: number): Promise<void> => {
    await api.delete(`/parts/${id}`);
  },

  importParts: async (file: File): Promise<{ imported: number }> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await api.post<{ imported: number }>('/parts/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },
};

// ── Prices ───────────────────────────────────────────
export const pricesApi = {
  getPrices: async (params?: Record<string, unknown>): Promise<PaginatedResponse<PriceEntry>> => {
    const { data } = await api.get<PaginatedResponse<PriceEntry>>('/prices/', { params });
    return data;
  },

  createPrice: async (payload: Partial<PriceEntry>): Promise<PriceEntry> => {
    const { data } = await api.post<PriceEntry>('/prices/', payload);
    return data;
  },

  importPrices: async (file: File, version: string): Promise<{ imported: number }> => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('version', version);
    const { data } = await api.post<{ imported: number }>('/prices/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },
};

// ── Customers ────────────────────────────────────────
export const customersApi = {
  getCustomers: async (params?: Record<string, unknown>): Promise<PaginatedResponse<Customer>> => {
    const { data } = await api.get<PaginatedResponse<Customer>>('/customers/', { params });
    return data;
  },

  getCustomer: async (id: number): Promise<Customer> => {
    const { data } = await api.get<Customer>(`/customers/${id}`);
    return data;
  },

  createCustomer: async (payload: Partial<Customer>): Promise<Customer> => {
    const { data } = await api.post<Customer>('/customers/', payload);
    return data;
  },

  updateCustomer: async (id: number, payload: Partial<Customer>): Promise<Customer> => {
    const { data } = await api.put<Customer>(`/customers/${id}`, payload);
    return data;
  },

  importCustomers: async (file: File): Promise<{ imported: number }> => {
    const formData = new FormData();
    formData.append('file', file);
    const { data } = await api.post<{ imported: number }>('/customers/import', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return data;
  },

  getTimeline: async (id: number, limit = 50) => {
    const { data } = await api.get(`/customers/${id}/timeline`, { params: { limit } });
    return data;
  },

  getActivityTimeline: async (id: number, limit = 50) => {
    const { data } = await api.get(`/customers/${id}/activity-timeline`, { params: { limit } });
    return data;
  },

  getHierarchy: async (id: number) => {
    const { data } = await api.get(`/customers/${id}/hierarchy`);
    return data;
  },

  setParent: async (id: number, parentId: number | null) => {
    const { data } = await api.patch(`/customers/${id}/parent`, null, {
      params: { parent_id: parentId },
    });
    return data;
  },

  getRollup: async (id: number) => {
    const { data } = await api.get(`/customers/${id}/rollup`);
    return data;
  },

  bulkAction: async (payload: {
    ids: number[];
    action: string;
    params?: Record<string, unknown>;
  }) => {
    const { data } = await api.post('/customers/bulk-action', payload);
    return data;
  },

  enrich: async (id: number): Promise<{ data: Record<string, unknown> }> => {
    const { data } = await api.post<{ data: Record<string, unknown> }>(`/customers/${id}/enrich`);
    return data;
  },

  getIntelligence: async (id: number, params?: Record<string, unknown>) => {
    const { data } = await api.get(`/customers/${id}/intelligence`, { params });
    return data;
  },

  getAccount360: async (id: number, opts?: { refresh?: boolean; timeline_limit?: number }) => {
    const { data } = await api.get(`/customers/${id}/account-360`, {
      params: {
        refresh: opts?.refresh ?? false,
        timeline_limit: opts?.timeline_limit ?? 40,
      },
    });
    return data;
  },

  listHighIntent: async (params?: { limit?: number }) => {
    const { data } = await api.get('/customers/high-intent', { params });
    return data;
  },

  pinCustomer: async (id: number) => {
    const { data } = await api.post(`/customers/${id}/pin`);
    return data;
  },

  unpinCustomer: async (id: number) => {
    const { data } = await api.delete(`/customers/${id}/pin`);
    return data;
  },
};

// ── Customer Health ─────────────────────────────────
export const customerHealthApi = {
  getCustomerHealth: async (id: number): Promise<CustomerHealthReport> => {
    const { data } = await api.get<CustomerHealthReport>(`/customers/health/${id}`);
    return data;
  },

  getHealthOverview: async (): Promise<HealthOverview> => {
    const { data } = await api.get<HealthOverview>('/customers/health/overview');
    return data;
  },

  getAtRiskCustomers: async (limit: number = 5): Promise<AtRiskResponse> => {
    const { data } = await api.get<AtRiskResponse>('/customers/health/at-risk', {
      params: { limit },
    });
    return data;
  },
};

// ── Quotes ───────────────────────────────────────────
export const quotesApi = {
  getQuotes: async (params?: Record<string, unknown>): Promise<PaginatedResponse<Quote>> => {
    const { data } = await api.get<PaginatedResponse<Quote>>('/quotes/', { params });
    return data;
  },

  getQuote: async (id: number): Promise<Quote> => {
    const { data } = await api.get<Quote>(`/quotes/${id}`);
    return data;
  },

  createQuote: async (payload: Record<string, unknown>): Promise<Quote> => {
    const { data } = await api.post<Quote>('/quotes/', payload);
    return data;
  },

  createQuoteFromEmail: async (emailId: number): Promise<Quote> => {
    const { data } = await api.post<Quote>(`/quotes/from-email/${emailId}`);
    return data;
  },

  updateQuote: async (id: number, payload: Record<string, unknown>): Promise<Quote> => {
    const { data } = await api.put<Quote>(`/quotes/${id}`, payload);
    return data;
  },

  approveQuote: async (id: number): Promise<Quote> => {
    const { data } = await api.patch<Quote>(`/quotes/${id}/approve`);
    return data;
  },

  sendQuote: async (id: number): Promise<Quote> => {
    const { data } = await api.post<Quote>(`/quotes/${id}/send`);
    return data;
  },

  downloadQuotePdf: async (id: number): Promise<void> => {
    try {
      const { data, headers } = await api.get(`/quotes/${id}/pdf`, {
        responseType: 'blob',
        _skipToast: true,
      } as ApiRequestConfig);
      const contentType = headers['content-type'];
      const mimeType = typeof contentType === 'string' ? contentType : 'application/pdf';
      const blob = new Blob([data], { type: mimeType });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `quote-${id}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err: unknown) {
      // When responseType is blob, error response body is a Blob - parse it
      const axiosErr = err as { response?: { data: unknown } };
      if (axiosErr?.response?.data instanceof Blob) {
        const text = await (axiosErr.response.data as Blob).text();
        try {
          const parsed = JSON.parse(text);
          axiosErr.response.data = parsed;
        } catch {
          /* keep as-is */
        }
      }
      throw err;
    }
  },
  getVersions: async (id: number) => {
    const { data } = await api.get(`/quotes/${id}/versions`);
    return data;
  },

  compareVersions: async (quoteId: number, otherId: number) => {
    const { data } = await api.get(`/quotes/${quoteId}/compare/${otherId}`);
    return data;
  },
};

// ── Analytics ────────────────────────────────────────
export const analyticsApi = {
  getTopParts: async (days: number = 30, limit: number = 10): Promise<TopPart[]> => {
    const { data } = await api.get<TopPart[]>('/analytics/top-parts', {
      params: { days, limit },
    });
    return data;
  },

  getMonthlyTrend: async (months: number = 6): Promise<TrendData[]> => {
    const { data } = await api.get<TrendData[]>('/analytics/monthly-trend', {
      params: { months },
    });
    return data;
  },

  getCategoryBreakdown: async (days: number = 30): Promise<Record<string, number>> => {
    const { data } = await api.get<Record<string, number>>('/analytics/category-breakdown', {
      params: { days },
    });
    return data;
  },

  getPartsWithoutPrice: async (days: number = 30): Promise<SparePart[]> => {
    const { data } = await api.get<SparePart[]>('/analytics/parts-without-price', {
      params: { days },
    });
    return data;
  },

  // Faz-3 endpoints
  getForecast: async (window = 30) => {
    const { data } = await api.get('/analytics/forecast', { params: { window } });
    return data;
  },
  getSlippage: async (noTouchDays = 7, limit = 50) => {
    const { data } = await api.get('/analytics/slippage', {
      params: { no_touch_days: noTouchDays, limit },
    });
    return data;
  },
  getFunnel: async (window = 30) => {
    const { data } = await api.get('/analytics/funnel', { params: { window } });
    return data;
  },
  getRepScorecards: async (window = 30) => {
    const { data } = await api.get('/analytics/rep-scorecards', { params: { window } });
    return data;
  },
  getDiscounts: async (window = 90) => {
    const { data } = await api.get('/analytics/discounts', { params: { window } });
    return data;
  },
  getSla: async (window = 30) => {
    const { data } = await api.get('/analytics/sla', { params: { window } });
    return data;
  },
  getWinLossReasons: async (window = 90) => {
    const { data } = await api.get('/analytics/win-loss-reasons', { params: { window } });
    return data;
  },
  getDataQuality: async () => {
    const { data } = await api.get('/analytics/data-quality');
    return data;
  },
  getRecordQuality: async (entityType: string, entityId: number) => {
    const { data } = await api.get(`/analytics/data-quality/${entityType}/${entityId}`);
    return data;
  },

  getActivityDrought: async (days = 7) => {
    const { data } = await api.get('/analytics/activity-drought', { params: { days } });
    return data;
  },

  getWaterfall: async (fromDate?: string, toDate?: string) => {
    const { data } = await api.get('/analytics/waterfall', {
      params: { from_date: fromDate, to_date: toDate },
    });
    return data;
  },

  getRevenueLeaks: async () => {
    const { data } = await api.get('/analytics/revenue-leaks');
    return data;
  },
};

export const opsApi = {
  getQueues: async () => {
    const { data } = await api.get('/ops/queues');
    return data;
  },
  getFeatureFlags: async (): Promise<Record<string, boolean>> => {
    const { data } = await api.get<{ data: Record<string, boolean> }>('/ops/feature-flags');
    return data?.data ?? {};
  },
};

export const savedViewsApi = {
  list: async (): Promise<{ views: SavedView[] }> => {
    const { data } = await api.get('/saved-views/');
    return data;
  },
  create: async (body: { name: string; route: string; query_json: string }) => {
    const { data } = await api.post('/saved-views/', body);
    return data;
  },
  remove: async (id: number) => {
    const { data } = await api.delete(`/saved-views/${id}`);
    return data;
  },
};

// ── Settings ─────────────────────────────────────────
export const settingsApi = {
  getSettings: async (): Promise<Record<string, unknown>> => {
    const { data } = await api.get<Record<string, unknown>>('/settings/');
    return data;
  },

  updateSettings: async (payload: Record<string, unknown>): Promise<Record<string, unknown>> => {
    const { data } = await api.put<Record<string, unknown>>('/settings/', payload);
    return data;
  },

  getEmailCredentials: async (): Promise<{
    email_address: string;
    email_password: string;
    imap_host: string;
    imap_port: number;
    smtp_host: string;
    smtp_port: number;
    is_configured: boolean;
  }> => {
    const { data } = await api.get('/settings/email-credentials');
    return data;
  },

  saveEmailCredentials: async (payload: {
    email_address: string;
    email_password: string;
    imap_host?: string;
    imap_port?: number;
    smtp_host?: string;
    smtp_port?: number;
  }): Promise<{ message: string; email_setup_completed: boolean }> => {
    const { data } = await api.post('/settings/email-credentials', payload);
    return data;
  },

  testEmailConnection: async (creds?: {
    email_address: string;
    email_password: string;
    imap_host?: string;
    imap_port?: number;
  }): Promise<{ success: boolean; message: string }> => {
    const { data } = await api.post('/settings/email-credentials/test', creds || {});
    return data;
  },

  getStageConfig: async () => {
    const { data } = await api.get('/settings/stage-config');
    return data;
  },

  updateStageConfig: async (stages: Record<string, unknown>[]) => {
    const { data } = await api.put('/settings/stage-config', { stages });
    return data;
  },

  getNotificationChannels: async (): Promise<{
    data: { slack_configured: boolean; teams_configured: boolean };
  }> => {
    const { data } = await api.get('/settings/notification-channels');
    return data;
  },

  testNotificationChannel: async (payload: {
    slack_url?: string;
    teams_url?: string;
  }): Promise<{ data: Record<string, boolean> }> => {
    const { data } = await api.post('/settings/notification-channels/test', payload);
    return data;
  },
};

// ── Notifications ───────────────────────────────────
export const notificationsApi = {
  // Backend wraps the list in `{notifications: [...]}` — unwrap here so
  // callers receive a plain array (matches `Notification[]` typing in
  // the Header component and was the root cause of "bell shows count
  // but list is empty" UAT bug — item #34). The unknown→T cast pushes
  // the responsibility for shape validation to the typed call site.
  getNotifications: async <T = unknown>(unreadOnly = false, limit = 20): Promise<T[]> => {
    const { data } = await api.get<{ notifications: T[] }>('/notifications/', {
      params: { unread_only: unreadOnly, limit },
    });
    return Array.isArray(data?.notifications) ? data.notifications : [];
  },
  getUnreadCount: async (): Promise<{ unread_count: number }> => {
    const { data } = await api.get<{ unread_count: number }>('/notifications/unread-count');
    return data;
  },
  markRead: async (id: number) => {
    await api.patch(`/notifications/${id}/read`);
  },
  markAllRead: async () => {
    await api.patch('/notifications/read-all');
  },
};

// ── Users ───────────────────────────────────────────
export const usersApi = {
  getUsers: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/users/', { params });
    return data;
  },
  toggleActive: async (id: number) => {
    const { data } = await api.patch(`/users/${id}/toggle-active`);
    return data;
  },
  changeRole: async (id: number, role: string) => {
    const { data } = await api.patch(`/users/${id}/role`, { role });
    return data;
  },
};

// ── Audit ───────────────────────────────────────────
export const auditApi = {
  getLogs: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/audit/', { params });
    return data;
  },
  exportCsv: async (params?: Record<string, unknown>): Promise<Blob> => {
    const response = await api.get('/audit/export/csv', {
      params,
      responseType: 'blob',
    });
    return response.data;
  },
  exportUserData: async (userId: number) => {
    const { data } = await api.get(`/audit/data-export/${userId}`);
    return data;
  },
};

// ── v2: Opportunities + Board ──────────────────────
export const opportunitiesApi = {
  list: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/opportunities/', { params });
    return data;
  },
  get: async (id: number) => {
    const { data } = await api.get(`/opportunities/${id}`);
    return data;
  },
  getIntelligence: async (id: number) => {
    const { data } = await api.get(`/opportunities/${id}/intelligence`);
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/opportunities/', payload);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.patch(`/opportunities/${id}`, payload);
    return data;
  },
  getTimeline: async (id: number, limit = 50) => {
    const { data } = await api.get(`/opportunities/${id}/timeline`, { params: { limit } });
    return data;
  },
  getStageRequirements: async (id: number) => {
    const { data } = await api.get(`/opportunities/${id}/stage-requirements`);
    return data;
  },

  getActivitySummary: async (id: number) => {
    const { data } = await api.get(`/opportunities/${id}/activity-summary`);
    return data;
  },

  bulkAction: async (payload: {
    ids: number[];
    action: string;
    params?: Record<string, unknown>;
  }) => {
    const { data } = await api.post('/opportunities/bulk-action', payload);
    return data;
  },
};

export const v4Api = {
  buildFeatureStore: async (snapshot_date?: string) => {
    const { data } = await api.post('/v4/feature-store/build', null, {
      params: snapshot_date ? { snapshot_date } : undefined,
    });
    return data as {
      snapshot_date: string;
      opportunities_upserted: number;
      accounts_upserted: number;
      reps_upserted: number;
    };
  },

  getLatestOpportunityFeatures: async (
    opportunityId: number,
  ): Promise<OpportunityFeaturesDailyLatest | null> => {
    const { data } = await api.get(`/v4/opportunities/${opportunityId}/features/latest`);
    return (data?.data as OpportunityFeaturesDailyLatest | null) ?? null;
  },
};

/** V4 additive alignment: live projections + shadow table reads + manager backfill (flags on backend). */
export const alignmentApi = {
  getNormalizedTimeline: async (
    opportunityId: number,
    params?: {
      limit?: number;
      include_signals?: boolean;
      include_legacy_opportunity_signals?: boolean;
    },
  ) => {
    const { data } = await api.get(
      `/v4/alignment/opportunities/${opportunityId}/normalized-timeline`,
      {
        params,
      },
    );
    return data as {
      opportunity_id: number;
      account_id: number | null;
      model_version: string;
      include_signals: boolean;
      include_legacy_opportunity_signals: boolean;
      items: Array<Record<string, unknown>>;
      total: number;
    };
  },

  getConversationSignals: async (
    opportunityId: number,
    params?: { limit?: number; include_legacy_opportunity_signals?: boolean },
  ) => {
    const { data } = await api.get(
      `/v4/alignment/opportunities/${opportunityId}/conversation-signals`,
      {
        params,
      },
    );
    return data as {
      opportunity_id: number;
      account_id: number | null;
      model_version: string;
      include_legacy_opportunity_signals: boolean;
      items: Array<Record<string, unknown>>;
      total: number;
    };
  },

  getShadowTimeline: async (opportunityId: number, limit = 500) => {
    const { data } = await api.get(`/v4/alignment/opportunities/${opportunityId}/shadow-timeline`, {
      params: { limit },
    });
    return data as {
      opportunity_id: number;
      model_version: string;
      items: Array<Record<string, unknown>>;
      total: number;
    };
  },

  /** sales_manager / operations — requires FEATURE_V4_SALES_EVENTS_SHADOW */
  postShadowSyncWindow: async (days: number) => {
    const { data } = await api.post('/v4/alignment/shadow/sync-window', { days });
    return data as {
      ok: boolean;
      window_days: number;
      counts: Record<string, number>;
    };
  },
};

/** V4 deal replay: persisted timeline snapshots (FEATURE_V4_DEAL_REPLAY). */
export const replayApi = {
  listSnapshots: async (opportunityId: number, limit = 60) => {
    const { data } = await api.get(`/v4/replay/opportunities/${opportunityId}/snapshots`, {
      params: { limit },
    });
    return data as {
      opportunity_id: number;
      items: Array<{
        snapshot_date: string;
        updated_at: string | null;
        timeline_item_count: number | undefined;
        feature_daily_present: boolean | undefined;
      }>;
      total: number;
    };
  },

  getSnapshot: async (opportunityId: number, snapshotDate: string) => {
    const { data } = await api.get(
      `/v4/replay/opportunities/${opportunityId}/snapshots/${snapshotDate}`,
    );
    return data as {
      opportunity_id: number;
      snapshot_date: string;
      source_timeline_version: string;
      frames: Record<string, unknown>;
      meta: Record<string, unknown>;
      updated_at: string | null;
    };
  },

  /** sales_manager / operations */
  postMaterialize: async (
    opportunityId: number,
    params?: {
      snapshot_date?: string;
      include_signals?: boolean;
      include_legacy_opportunity_signals?: boolean;
      timeline_limit?: number;
    },
  ) => {
    const { data } = await api.post(`/v4/replay/opportunities/${opportunityId}/materialize`, null, {
      params,
    });
    return data as {
      ok: boolean;
      opportunity_id: number;
      snapshot_date: string;
      timeline_item_count: number | undefined;
    };
  },
};

/** V4 Sales DNA: miner output in v4_sales_dna_snapshots (FEATURE_V4_SALES_DNA). */
export const dnaApi = {
  listSnapshots: async (opportunityId: number, limit = 60) => {
    const { data } = await api.get(`/v4/dna/opportunities/${opportunityId}/snapshots`, {
      params: { limit },
    });
    return data as {
      opportunity_id: number;
      items: Array<{
        snapshot_date: string;
        updated_at: string | null;
        miner_version: string;
        feature_daily_present: boolean | undefined;
      }>;
      total: number;
    };
  },

  getLatest: async (opportunityId: number) => {
    const { data } = await api.get(`/v4/dna/opportunities/${opportunityId}/latest`);
    return data as {
      opportunity_id: number;
      snapshot_date: string;
      traits: Record<string, unknown>;
      meta: Record<string, unknown>;
      updated_at: string | null;
    };
  },

  getSnapshot: async (opportunityId: number, snapshotDate: string) => {
    const { data } = await api.get(
      `/v4/dna/opportunities/${opportunityId}/snapshots/${snapshotDate}`,
    );
    return data as {
      opportunity_id: number;
      snapshot_date: string;
      traits: Record<string, unknown>;
      meta: Record<string, unknown>;
      updated_at: string | null;
    };
  },

  postMaterialize: async (opportunityId: number, snapshot_date?: string) => {
    const { data } = await api.post(`/v4/dna/opportunities/${opportunityId}/materialize`, null, {
      params: snapshot_date ? { snapshot_date } : undefined,
    });
    return data as {
      ok: boolean;
      opportunity_id: number;
      snapshot_date: string;
      risk_posture: string | undefined;
      coaching_hooks: string[] | undefined;
    };
  },
};

/**
 * Driver behind a buyer-state classification or a decision-gap.
 * Each driver is a small dict the backend builds from feature-store
 * deltas (stakeholder added, discount widened, meeting held, etc.).
 * Modelled here as an open-ended record so unknown driver types
 * still render ``label`` + ``magnitude`` without breaking the page.
 */
export interface IntelligenceDriver {
  driver_type?: string;
  label?: string;
  magnitude?: number | null;
  direction?: 'positive' | 'negative' | 'neutral';
  weight?: number;
  evidence?: string;
  [key: string]: unknown;
}

export const buyerStateApi = {
  getTimeline: async (opportunityId: number, limit = 30) => {
    const { data } = await api.get(`/buyer-state/opportunities/${opportunityId}/timeline`, {
      params: { limit },
    });
    return data as {
      items: Array<{
        snapshot_date: string;
        state: string;
        confidence: number;
        drivers: IntelligenceDriver[];
      }>;
      total: number;
    };
  },
};

export const decisionGapsApi = {
  listForOpportunity: async (opportunityId: number) => {
    const { data } = await api.get(`/decision-gaps/opportunities/${opportunityId}`);
    return data as {
      opportunity_id: number;
      items: Array<{
        id: number;
        gap_type: string;
        severity: string;
        expected_roles: string[];
        observed_roles: string[];
        recommended_actions: string[];
        drivers: IntelligenceDriver[];
        created_at: string | null;
      }>;
      total: number;
    };
  },
  cockpitList: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/decision-gaps/cockpit/list', { params });
    return data as {
      items: Array<{
        id: number;
        opportunity_id: number;
        title: string;
        stage: string;
        amount: number | null;
        currency: string;
        gap_type: string;
        severity: string;
        // ``recommended_action`` is the headline (legacy string).
        // ``recommended_actions`` is the full array — render this in
        // new UI; the singular field stays for backwards compat.
        recommended_action: string | null;
        recommended_actions: string[];
        created_at: string | null;
      }>;
      total: number;
    };
  },
};

export const networkBenchmarksApi = {
  getLatestSegments: async (limit = 50) => {
    const { data } = await api.get('/v4/benchmarks/segments/latest', { params: { limit } });
    return data as {
      snapshot_date: string | null;
      items: Array<{
        segment_key: string;
        sample_size: number;
        win_rate_90d: number | null;
        followup_median_days: number | null;
        avg_discount_pct: number | null;
        avg_stakeholder_count: number | null;
        objection_rate_14d: number | null;
      }>;
      total: number;
    };
  },
  getOpportunityGap: async (opportunityId: number) => {
    const { data } = await api.get(`/v4/benchmarks/opportunities/${opportunityId}/gap`);
    return data as {
      data: null | {
        segment_key: string;
        snapshot_date: string;
        gap_score: number;
        drivers: Array<{ label: string; impact: number; value?: unknown }>;
        benchmark_context: Record<string, unknown>;
        you: Record<string, unknown>;
        recommended_actions: string[];
        model_version: string;
      };
    };
  },
};

export const boardApi = {
  getKanban: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/board/kanban', { params });
    return data;
  },
  getSummary: async (window = 30) => {
    const { data } = await api.get('/board/summary', { params: { window } });
    return data;
  },
};

// ── Leads ──────────────────────────────────────────────
export const leadsApi = {
  list: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/leads/', { params });
    return data;
  },
  get: async (id: number) => {
    const { data } = await api.get(`/leads/${id}`);
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/leads/', payload);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.patch(`/leads/${id}`, payload);
    return data;
  },
  convert: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.post(`/leads/${id}/convert`, payload);
    return data;
  },
  rescore: async (id: number) => {
    const { data } = await api.post(`/leads/${id}/rescore`);
    return data;
  },

  bulkAction: async (payload: {
    ids: number[];
    action: string;
    params?: Record<string, unknown>;
  }) => {
    const { data } = await api.post('/leads/bulk-action', payload);
    return data;
  },
};

// ── Approvals ──────────────────────────────────────────
export const approvalsApi = {
  getRules: async () => {
    const { data } = await api.get('/approvals/rules');
    return data;
  },
  createRule: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/approvals/rules', payload);
    return data;
  },
  updateRule: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/approvals/rules/${id}`, payload);
    return data;
  },
  deleteRule: async (id: number) => {
    await api.delete(`/approvals/rules/${id}`);
  },
  getPending: async () => {
    const { data } = await api.get('/approvals/pending');
    return data;
  },
  approve: async (id: number, comments = '') => {
    const { data } = await api.post(`/approvals/${id}/approve`, { comments });
    return data;
  },
  reject: async (id: number, comments = '') => {
    const { data } = await api.post(`/approvals/${id}/reject`, { comments });
    return data;
  },
  getHistory: async (entityType: string, entityId: number) => {
    const { data } = await api.get('/approvals/history', {
      params: { entity_type: entityType, entity_id: entityId },
    });
    return data;
  },
};

// ── Forecast ───────────────────────────────────────────
export const forecastApi = {
  createAdjustment: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/forecast/adjustments', payload);
    return data;
  },
  getAdjustments: async (opportunityId: number) => {
    const { data } = await api.get('/forecast/adjustments', {
      params: { opportunity_id: opportunityId },
    });
    return data;
  },
  getSnapshots: async (startDate?: string, endDate?: string) => {
    const { data } = await api.get('/forecast/snapshots', {
      params: { start_date: startDate, end_date: endDate },
    });
    return data;
  },
  takeSnapshot: async () => {
    const { data } = await api.post('/forecast/snapshot');
    return data;
  },
  getWoW: async (weeks = 4) => {
    const { data } = await api.get('/forecast/wow', { params: { weeks } });
    return data;
  },
  getTeamRollup: async () => {
    const { data } = await api.get('/forecast/team-rollup');
    return data;
  },

  getAccuracy: async (quarter?: string) => {
    const { data } = await api.get('/forecast/accuracy', {
      params: quarter ? { quarter } : undefined,
    });
    return data;
  },
  getHybrid: async (ownerId?: number) => {
    const { data } = await api.get('/forecast/hybrid', {
      params: ownerId != null ? { owner_id: ownerId } : undefined,
    });
    return data;
  },
  getWowComparison: async () => {
    const { data } = await api.get('/forecast/wow');
    return data;
  },
};

// ── Deal Health ────────────────────────────────────────
export const dealHealthApi = {
  get: async (opportunityId: number) => {
    const { data } = await api.get(`/deal-health/${opportunityId}`);
    return data;
  },
  getOverview: async (ownerId?: number) => {
    const { data } = await api.get('/deal-health/overview/all', { params: { owner_id: ownerId } });
    return data;
  },
  getAtRisk: async (threshold = 40) => {
    const { data } = await api.get('/deal-health/at-risk/list', { params: { threshold } });
    return data;
  },
};

// ── Webhooks ───────────────────────────────────────────
export const webhooksApi = {
  list: async () => {
    const { data } = await api.get('/webhooks/');
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/webhooks/', payload);
    return data;
  },
  get: async (id: number) => {
    const { data } = await api.get(`/webhooks/${id}`);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.patch(`/webhooks/${id}`, payload);
    return data;
  },
  remove: async (id: number) => {
    await api.delete(`/webhooks/${id}`);
  },
  getDeliveries: async (id: number, limit = 20) => {
    const { data } = await api.get(`/webhooks/${id}/deliveries`, { params: { limit } });
    return data;
  },
  test: async (id: number) => {
    const { data } = await api.post(`/webhooks/${id}/test`);
    return data;
  },
};

// ── Teams / Sharing ────────────────────────────────────
export const teamsApi = {
  getMembers: async (customerId: number) => {
    const { data } = await api.get(`/customers/${customerId}/team`);
    return data;
  },
  addMember: async (customerId: number, userId: number, role = 'member') => {
    const { data } = await api.post(`/customers/${customerId}/team`, { user_id: userId, role });
    return data;
  },
  removeMember: async (customerId: number, userId: number) => {
    await api.delete(`/customers/${customerId}/team/${userId}`);
  },
  getSharingRules: async () => {
    const { data } = await api.get('/sharing-rules/');
    return data;
  },
  createSharingRule: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/sharing-rules/', payload);
    return data;
  },
  deleteSharingRule: async (id: number) => {
    await api.delete(`/sharing-rules/${id}`);
  },
};

// ── Reports (Self-Service Builder) ─────────────────────
export const reportsApi = {
  getTemplates: async () => {
    const { data } = await api.get('/reports/templates');
    return data;
  },
  createTemplate: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/reports/templates', payload);
    return data;
  },
  updateTemplate: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/reports/templates/${id}`, payload);
    return data;
  },
  deleteTemplate: async (id: number) => {
    await api.delete(`/reports/templates/${id}`);
  },
  execute: async (id: number) => {
    const { data } = await api.post(`/reports/templates/${id}/execute`);
    return data;
  },
  preview: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/reports/preview', payload);
    return data;
  },
  exportCsv: async (id: number) => {
    const { data } = await api.get(`/reports/templates/${id}/export`, {
      params: { format: 'csv' },
    });
    return data;
  },
  getAvailableColumns: async (entityType: string) => {
    const { data } = await api.get('/reports/available-columns', {
      params: { entity_type: entityType },
    });
    return data;
  },
  exportExcel: async (id: number, reportName: string): Promise<void> => {
    const response = await api.get(`/reports/templates/${id}/export-excel`, {
      responseType: 'blob',
      _skipToast: true,
    } as ApiRequestConfig);
    const blob = new Blob([response.data as BlobPart], {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${reportName}.xlsx`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};

// ── Revenue Cockpit ───────────────────────────────────
export const cockpitApi = {
  getKpis: async () => {
    const { data } = await api.get('/cockpit/kpis');
    return data;
  },
  getSignals: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/cockpit/signals', { params });
    return data;
  },
  getRiskyAccounts: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/cockpit/risky-accounts', { params });
    return data;
  },
  getActions: async () => {
    const { data } = await api.get('/cockpit/actions');
    return data;
  },
  getTrends: async () => {
    const { data } = await api.get('/cockpit/trends');
    return data;
  },
  resolveSignal: async (id: number) => {
    const { data } = await api.post(`/cockpit/signals/${id}/resolve`);
    return data;
  },
  getMomentum: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/cockpit/momentum', { params });
    return data;
  },
  getStallingDeals: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/cockpit/buyer-state/stalling', { params });
    return data;
  },
};

// ── Insights ───────────────────────────────────────────
export const insightsApi = {
  getSignals: async (windowDays = 30) => {
    const { data } = await api.get('/insights/signals', { params: { window: windowDays } });
    return data;
  },
  getSignalsTrends: async (windowDays = 30) => {
    const { data } = await api.get('/insights/signals/trends', { params: { window: windowDays } });
    return data;
  },
  getConversationInsights: async (windowDays = 30) => {
    const { data } = await api.get('/insights/conversation-insights', {
      params: { window: windowDays },
    });
    return data;
  },
  searchConversations: async (params: {
    q: string;
    stage?: string;
    signal_type?: string;
    owner_id?: number;
    page?: number;
    page_size?: number;
  }) => {
    const { data } = await api.get('/insights/conversation-search', { params });
    return data;
  },
};

// ── V10 Spare Parts Intelligence ────────────────────────
// Read-only intelligence layer over SparePart × PriceEntry × QuoteItem.
// All endpoints gated server-side by FEATURE_V10_PARTS_INTEL — when
// the flag is off the backend returns 404 and we surface "feature not
// available" so the UI degrades gracefully.
export const v10PartsIntelApi = {
  getSummary: async () => {
    const { data } = await api.get('/v10/parts-intel/summary');
    return data;
  },
  getVelocity: async (tier?: 'A' | 'B' | 'C') => {
    const { data } = await api.get('/v10/parts-intel/velocity', {
      params: tier ? { tier } : undefined,
    });
    return data;
  },
  getHeatmap: async (windowDays = 180, partId?: number) => {
    const { data } = await api.get('/v10/parts-intel/heatmap', {
      params: { window_days: windowDays, part_id: partId },
    });
    return data;
  },
  getDeadStock: async (minIdleDays = 180, limit = 100) => {
    const { data } = await api.get('/v10/parts-intel/dead-stock', {
      params: { min_idle_days: minIdleDays, limit },
    });
    return data;
  },
  getInflationTax: async (months = 12) => {
    const { data } = await api.get('/v10/parts-intel/inflation-tax', {
      params: { months },
    });
    return data;
  },
  getStalePricing: async (maxAgeDays = 180, limit = 100) => {
    const { data } = await api.get('/v10/parts-intel/stale-pricing', {
      params: { max_age_days: maxAgeDays, limit },
    });
    return data;
  },
  getMarginHealth: async (limit = 100) => {
    const { data } = await api.get('/v10/parts-intel/margin-health', {
      params: { limit },
    });
    return data;
  },
  getObsolescenceWatch: async (topN = 20) => {
    const { data } = await api.get('/v10/parts-intel/obsolescence-watch', {
      params: { top_n: topN },
    });
    return data;
  },
  getEolRisk: async (partId: number) => {
    const { data } = await api.get(`/v10/parts-intel/parts/${partId}/eol-risk`);
    return data;
  },
  getLastTimeBuy: async () => {
    const { data } = await api.get('/v10/parts-intel/last-time-buy');
    return data;
  },
  getDataHealth: async () => {
    const { data } = await api.get('/v10/parts-intel/data-health');
    return data;
  },
  getDuplicates: async (threshold = 0.85, limit = 100) => {
    const { data } = await api.get('/v10/parts-intel/duplicates', {
      params: { threshold, limit },
    });
    return data;
  },
  getOrphanPricing: async (limit = 200) => {
    const { data } = await api.get('/v10/parts-intel/orphan-pricing', {
      params: { limit },
    });
    return data;
  },
  getSubstitutions: async (partId: number, limit = 20) => {
    const { data } = await api.get(`/v10/parts-intel/parts/${partId}/substitutions`, {
      params: { limit },
    });
    return data;
  },
  getCrossCustomer: async (partId: number, months = 12, limit = 50) => {
    const { data } = await api.get(`/v10/parts-intel/parts/${partId}/cross-customer`, {
      params: { months, limit },
    });
    return data;
  },
  getSegmentAffinity: async (partId: number, months = 12) => {
    const { data } = await api.get(`/v10/parts-intel/parts/${partId}/segment-affinity`, {
      params: { months },
    });
    return data;
  },
};

// ── Playbooks ─────────────────────────────────────────
export const playbookApi = {
  list: async () => {
    const { data } = await api.get('/playbooks/');
    return data;
  },
  get: async (id: number) => {
    const { data } = await api.get(`/playbooks/${id}`);
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/playbooks/', payload);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/playbooks/${id}`, payload);
    return data;
  },
  remove: async (id: number) => {
    await api.delete(`/playbooks/${id}`);
  },
  getTemplates: async () => {
    const { data } = await api.get('/playbooks/templates');
    return data;
  },
  getAnalytics: async () => {
    const { data } = await api.get('/playbooks/analytics');
    return data;
  },
  getExecutions: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/playbooks/executions', { params });
    return data;
  },
  cancelExecution: async (id: number) => {
    const { data } = await api.post(`/playbooks/executions/${id}/cancel`);
    return data;
  },
};

// ── Coaching ──────────────────────────────────────────
export const coachingApi = {
  getOverview: async () => {
    const { data } = await api.get('/coaching/overview');
    return data;
  },
  getRepReport: async (id: number) => {
    const { data } = await api.get(`/coaching/rep/${id}`);
    return data;
  },
  listPlans: async () => {
    const { data } = await api.get('/coaching/plans');
    return data;
  },
  createPlan: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/coaching/plans', payload);
    return data;
  },
  getRepTrends: async (userId: number) => {
    const { data } = await api.get(`/coaching/rep/${userId}/trends`);
    return data;
  },
  getBenchmarks: async () => {
    const { data } = await api.get('/coaching/benchmarks');
    return data;
  },
};

// ── AI Engine ─────────────────────────────────────────
export const aiApi = {
  summarize: async (payload: {
    entity_type: string;
    entity_id: number;
    focus?: string;
    force?: boolean;
  }) => {
    const { data } = await api.post('/ai/summarize', payload);
    return data;
  },
  summarizeChanges: async (payload: {
    entity_type: 'opportunity' | 'customer';
    entity_id: number;
    days?: number;
    force?: boolean;
  }) => {
    const { data } = await api.post('/ai/summarize/changes', payload);
    return data;
  },
  meetingPrep: async (customerId: number) => {
    const { data } = await api.post<{ prep: string; customer_id: number }>('/ai/meeting-prep', {
      customer_id: customerId,
    });
    return data;
  },
  suggestPipeline: async (payload: { opportunity_id: number }) => {
    const { data } = await api.post('/ai/suggest-pipeline-update', payload);
    return data;
  },
  extractSignals: async (payload: { opportunity_id?: number; email_id?: number }) => {
    const { data } = await api.post('/ai/extract-signals', payload);
    return data;
  },
  getSignals: async (opportunityId: number) => {
    const { data } = await api.get(`/ai/signals/${opportunityId}`);
    return data;
  },
  listTasks: async (status = 'open') => {
    const { data } = await api.get('/ai/tasks', { params: { status } });
    return data;
  },
  createTask: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/ai/tasks', payload);
    return data;
  },
  updateTask: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.patch(`/ai/tasks/${id}`, payload);
    return data;
  },
  dealRisk: async (opportunityId: number) => {
    const { data } = await api.post(`/ai/deal-risk/${opportunityId}`);
    return data;
  },
  generateActions: async (payload: { opportunity_id: number; max_actions?: number }) => {
    const { data } = await api.post('/ai/generate-actions', payload);
    return data;
  },
  competitiveIntel: async (days = 90) => {
    const { data } = await api.get('/ai/competitive-intel', { params: { days } });
    return data;
  },
  predictClose: async (oppId: number) => {
    const { data } = await api.post(`/ai/predict-close/${oppId}`);
    return data;
  },
  predictChurn: async (customerId: number) => {
    const { data } = await api.post(`/ai/predict-churn/${customerId}`);
    return data;
  },
  crawlCompetitors: async () => {
    const { data } = await api.post('/ai/crawl-competitors');
    return data;
  },
  crawlCompetitor: async (name: string) => {
    const { data } = await api.post(`/ai/crawl-competitor/${name}`);
    return data;
  },
  ragStatus: async () => {
    const { data } = await api.get('/ai/rag/status');
    return data;
  },
  draftReply: async (payload: {
    email_id?: number;
    draft_type?: string;
    tone?: string;
    template_context?: Record<string, string>;
  }) => {
    const { data } = await api.post('/ai/email/draft-reply', payload);
    return data;
  },
};

// ── Pricing Admin ─────────────────────────────────────
export const pricingApi = {
  getTiers: async (priceEntryId: number) => {
    const { data } = await api.get(`/pricing/tiers/${priceEntryId}`);
    return data;
  },
  createTier: async (payload: {
    price_entry_id: number;
    min_qty: number;
    max_qty?: number;
    unit_price: number;
    discount_pct?: number;
  }) => {
    const { data } = await api.post('/pricing/tiers', payload);
    return data;
  },
  deleteTier: async (tierId: number) => {
    const { data } = await api.delete(`/pricing/tiers/${tierId}`);
    return data;
  },
  getCustomerPricing: async (customerId: number) => {
    const { data } = await api.get(`/pricing/customer/${customerId}`);
    return data;
  },
  createCustomerPricing: async (
    customerId: number,
    payload: {
      spare_part_id: number;
      contracted_price: number;
      currency?: string;
      discount_pct?: number;
      valid_from?: string;
      valid_until?: string;
      notes?: string;
    },
  ) => {
    const { data } = await api.post(`/pricing/customer/${customerId}`, payload);
    return data;
  },
  updateCustomerPricing: async (
    customerId: number,
    pricingId: number,
    payload: Record<string, unknown>,
  ) => {
    const { data } = await api.put(`/pricing/customer/${customerId}/${pricingId}`, payload);
    return data;
  },
  deleteCustomerPricing: async (customerId: number, pricingId: number) => {
    const { data } = await api.delete(`/pricing/customer/${customerId}/${pricingId}`);
    return data;
  },
  lookup: async (params: { spare_part_id: number; customer_id?: number; quantity?: number }) => {
    const { data } = await api.get('/pricing/lookup', { params });
    return data;
  },
  updateMargin: async (sparePartId: number, minMarginPct: number) => {
    const { data } = await api.patch(`/pricing/margin/${sparePartId}`, {
      min_margin_pct: minMarginPct,
    });
    return data;
  },
};

// ── Activities ────────────────────────────────────────
// ── Dashboard Builder ─────────────────────────────────
export const dashboardsApi = {
  list: async () => {
    const { data } = await api.get('/dashboards/');
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/dashboards/', payload);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/dashboards/${id}`, payload);
    return data;
  },
  remove: async (id: number) => {
    await api.delete(`/dashboards/${id}`);
  },
  execute: async (id: number) => {
    const { data } = await api.get(`/dashboards/${id}/execute`);
    return data;
  },
};

// ── Engagement ────────────────────────────────────────
export const engagementApi = {
  listTranscripts: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/engagement/transcripts/', { params });
    return data;
  },
  createTranscript: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/engagement/transcripts/', payload);
    return data;
  },
  summarizeTranscript: async (id: number) => {
    const { data } = await api.post(`/engagement/transcripts/${id}/summarize`);
    return data;
  },
  searchTranscripts: async (params: Record<string, unknown>) => {
    const { data } = await api.get('/engagement/transcripts/search', { params });
    return data;
  },
  listKeywordPacks: async () => {
    const { data } = await api.get('/engagement/keyword-packs/');
    return data;
  },
  createKeywordPack: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/engagement/keyword-packs/', payload);
    return data;
  },
  listSequences: async () => {
    const { data } = await api.get('/engagement/sequences/');
    return data;
  },
  getSequence: async (id: number) => {
    const { data } = await api.get(`/engagement/sequences/${id}`);
    return data;
  },
  createSequence: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/engagement/sequences/', payload);
    return data;
  },
  updateSequence: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.patch(`/engagement/sequences/${id}`, payload);
    return data;
  },
  enrollInSequence: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/engagement/sequences/enroll', payload);
    return data;
  },
  listEnrollments: async (sequenceId?: number) => {
    const { data } = await api.get('/engagement/sequences/enrollments', {
      params: sequenceId ? { sequence_id: sequenceId } : {},
    });
    return data;
  },
  pauseEnrollment: async (enrollmentId: number) => {
    const { data } = await api.patch(`/engagement/sequences/enrollments/${enrollmentId}/pause`);
    return data;
  },
  resumeEnrollment: async (enrollmentId: number) => {
    const { data } = await api.patch(`/engagement/sequences/enrollments/${enrollmentId}/resume`);
    return data;
  },
  listSegments: async () => {
    const { data } = await api.get('/engagement/segments/');
    return data;
  },
  createSegment: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/engagement/segments/', payload);
    return data;
  },
  getSegmentCustomers: async (id: number) => {
    const { data } = await api.get(`/engagement/segments/${id}/customers`);
    return data;
  },
  getCoachingScorecards: async (window = 30) => {
    const { data } = await api.get('/engagement/coaching/scorecards', { params: { window } });
    return data;
  },
};

// ── Compliance (KVKK) ─────────────────────────────────
export const complianceApi = {
  getConsent: async (customerId: number) => {
    const { data } = await api.get(`/compliance/consent/${customerId}`);
    return data;
  },
  recordConsent: async (customerId: number, payload: Record<string, unknown>) => {
    const { data } = await api.post(`/compliance/consent/${customerId}`, payload);
    return data;
  },
  exportData: async (customerId: number) => {
    const { data } = await api.post(`/compliance/data-export/${customerId}`);
    return data;
  },
  anonymizeData: async (customerId: number) => {
    const { data } = await api.post(`/compliance/data-delete/${customerId}`);
    return data;
  },
  getRetentionReport: async () => {
    const { data } = await api.get('/compliance/retention-report');
    return data;
  },
  getAuditTrail: async (customerId: number) => {
    const { data } = await api.get(`/compliance/audit-trail/${customerId}`);
    return data;
  },
  listRetentionPolicies: async () => {
    const { data } = await api.get('/compliance/retention-policies');
    return data;
  },
  createRetentionPolicy: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/compliance/retention-policies', payload);
    return data;
  },
  updateRetentionPolicy: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/compliance/retention-policies/${id}`, payload);
    return data;
  },
  deleteRetentionPolicy: async (id: number) => {
    await api.delete(`/compliance/retention-policies/${id}`);
  },
  createBreach: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/compliance/breach', payload);
    return data;
  },
  updateBreach: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.patch(`/compliance/breach/${id}`, payload);
    return data;
  },
  listBreaches: async (status?: string) => {
    const { data } = await api.get('/compliance/breaches', { params: status ? { status } : {} });
    return data;
  },
};

// ── Integrations ──────────────────────────────────────
export const integrationsApi = {
  getCalendarAuthUrl: async (provider = 'google') => {
    const { data } = await api.get('/integrations/calendar/auth-url', { params: { provider } });
    return data;
  },
  getCalendarStatus: async () => {
    const { data } = await api.get('/integrations/calendar/status');
    return data;
  },
  getCalendarHealth: async () => {
    const { data } = await api.get('/integrations/calendar/health');
    return data;
  },
  connectCalendar: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/integrations/calendar/connect', payload);
    return data;
  },
  syncCalendar: async () => {
    const { data } = await api.post('/integrations/calendar/sync');
    return data;
  },
  createCalendarEvent: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/integrations/calendar/events', payload);
    return data;
  },
  linkCalendarEvent: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/integrations/calendar/link-event', payload);
    return data;
  },
  getEsignStatus: async () => {
    const { data } = await api.get('/integrations/esign/status');
    return data;
  },
  connectEsign: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/integrations/esign/connect', payload);
    return data;
  },
  sendForSignature: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/integrations/esign/send', payload);
    return data;
  },
};

// ── Custom Fields ─────────────────────────────────────
export const customFieldsApi = {
  list: async (entityType = 'customer') => {
    const { data } = await api.get('/custom-fields/', { params: { entity_type: entityType } });
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/custom-fields/', payload);
    return data;
  },
  remove: async (id: number) => {
    const { data } = await api.delete(`/custom-fields/${id}`);
    return data;
  },
  getValues: async (entityType: string, entityId: number) => {
    const { data } = await api.get(`/custom-fields/values/${entityType}/${entityId}`);
    return data;
  },
  setValue: async (entityType: string, entityId: number, payload: Record<string, unknown>) => {
    const { data } = await api.post(`/custom-fields/values/${entityType}/${entityId}`, payload);
    return data;
  },
};

// ── Field Permissions ─────────────────────────────────
export const fieldPermissionsApi = {
  list: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/field-permissions/', { params });
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/field-permissions/', payload);
    return data;
  },
  remove: async (id: number) => {
    const { data } = await api.delete(`/field-permissions/${id}`);
    return data;
  },
};

// ── Product Rules ─────────────────────────────────────
export const productRulesApi = {
  list: async () => {
    const { data } = await api.get('/product-rules/');
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/product-rules/', payload);
    return data;
  },
  remove: async (id: number) => {
    const { data } = await api.delete(`/product-rules/${id}`);
    return data;
  },
  evaluate: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/product-rules/evaluate', payload);
    return data;
  },
};

// ── Workflow Rules ───────────────────────────────────
export const workflowRulesApi = {
  list: async () => {
    const { data } = await api.get('/workflow-rules/');
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/workflow-rules/', payload);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/workflow-rules/${id}`, payload);
    return data;
  },
  remove: async (id: number) => {
    await api.delete(`/workflow-rules/${id}`);
  },
};

// ── Activities ──────────────────────────────────────
export const activitiesApi = {
  getFeed: async (params?: { since?: string; limit?: number }) => {
    const { data } = await api.get('/activities/feed', { params });
    return data;
  },
  log: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/activities/', payload);
    return data;
  },
  list: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/activities/', { params });
    return data;
  },
  getMetrics: async (window = 30) => {
    const { data } = await api.get('/activities/metrics', { params: { window } });
    return data;
  },
};

// ── Duplicates ──────────────────────────────────────
export const duplicatesApi = {
  check: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/duplicates/check', payload);
    return data;
  },
  mergePreview: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/duplicates/merge/preview', payload);
    return data;
  },
  merge: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/duplicates/merge', payload);
    return data;
  },
};

// ── Product Bundles (CPQ) ────────────────────────────
export const bundlesApi = {
  list: async () => {
    const { data } = await api.get('/bundles/');
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/bundles/', payload);
    return data;
  },
  remove: async (id: number) => {
    const { data } = await api.delete(`/bundles/${id}`);
    return data;
  },
  toQuoteItems: async (id: number) => {
    const { data } = await api.post(`/bundles/${id}/to-quote-items`);
    return data;
  },
};

// ── Email Templates ─────────────────────────────────
export const emailTemplatesApi = {
  list: async () => {
    const { data } = await api.get('/email-templates/');
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/email-templates/', payload);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/email-templates/${id}`, payload);
    return data;
  },
  remove: async (id: number) => {
    await api.delete(`/email-templates/${id}`);
  },
  send: async (id: number, payload: { to_email: string; context: Record<string, string> }) => {
    const { data } = await api.post(`/email-templates/${id}/send`, payload);
    return data;
  },
  getVariables: async () => {
    const { data } = await api.get('/email-templates/variables');
    return data;
  },
};

// ── Comments ────────────────────────────────────────
export const commentsApi = {
  list: async (params: Record<string, unknown>) => {
    const { data } = await api.get('/comments/', { params });
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/comments/', payload);
    return data;
  },
  remove: async (id: number) => {
    await api.delete(`/comments/${id}`);
  },
};

// ── Leaderboard ────────────────────────────────────
export const leaderboardApi = {
  getLeaderboard: async (period: string = 'month', metric: string = 'revenue') => {
    const { data } = await api.get('/leaderboard/', { params: { period, metric } });
    return data;
  },
  getAchievements: async () => {
    const { data } = await api.get('/leaderboard/achievements');
    return data;
  },
  getUserAchievements: async (userId: number) => {
    const { data } = await api.get(`/leaderboard/achievements/${userId}`);
    return data;
  },
};

// ── Deal Rooms ──────────────────────────────────────
export const dealRoomsApi = {
  list: async () => {
    const { data } = await api.get('/deal-rooms/');
    return data;
  },
  create: async (payload: { opportunity_id: number; name: string; welcome_message?: string }) => {
    const { data } = await api.post('/deal-rooms/', payload);
    return data;
  },
  get: async (id: number) => {
    const { data } = await api.get(`/deal-rooms/${id}`);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/deal-rooms/${id}`, payload);
    return data;
  },
  remove: async (id: number) => {
    const { data } = await api.delete(`/deal-rooms/${id}`);
    return data;
  },
  getPublic: async (token: string) => {
    const { data } = await api.get(`/deal-rooms/public/${token}`);
    return data;
  },
  updateAction: async (token: string, payload: { item_index: number; completed: boolean }) => {
    const { data } = await api.post(`/deal-rooms/public/${token}/action`, payload);
    return data;
  },
};

// ── Documents ────────────────────────────────────────
export const documentsApi = {
  share: async (payload: {
    quote_id?: number;
    file_name: string;
    file_url: string;
    shared_with_email: string;
  }) => {
    const { data } = await api.post('/documents/share', payload);
    return data;
  },
  list: async () => {
    const { data } = await api.get('/documents/');
    return data;
  },
  getAnalytics: async (id: number) => {
    const { data } = await api.get(`/documents/${id}/analytics`);
    return data;
  },
  track: async (token: string) => {
    const { data } = await api.get(`/documents/track/${token}`);
    return data;
  },
};

// ── Meetings ────────────────────────────────────────
export const meetingsApi = {
  listLinks: async () => {
    const { data } = await api.get('/meetings/links');
    return data;
  },
  createLink: async (payload: { title: string; duration_minutes?: number }) => {
    const { data } = await api.post('/meetings/links', payload);
    return data;
  },
  deactivateLink: async (id: number) => {
    const { data } = await api.delete(`/meetings/links/${id}`);
    return data;
  },
  getBookingPage: async (slug: string) => {
    const { data } = await api.get(`/meetings/book/${slug}`);
    return data;
  },
  createBooking: async (
    slug: string,
    payload: {
      booker_name: string;
      booker_email: string;
      scheduled_at: string;
      notes?: string;
    },
  ) => {
    const { data } = await api.post(`/meetings/book/${slug}`, payload);
    return data;
  },
  listBookings: async () => {
    const { data } = await api.get('/meetings/bookings');
    return data;
  },
  schedulePlaceholder: async (payload: {
    title: string;
    start_at: string;
    duration_minutes?: number;
    opportunity_id?: number;
  }) => {
    const { data } = await api.post('/meetings/schedule-placeholder', payload);
    return data;
  },
};

// ── Subscriptions ──────────────────────────────────
export const subscriptionsApi = {
  list: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/subscriptions/', { params });
    return data;
  },
  get: async (id: number) => {
    const { data } = await api.get(`/subscriptions/${id}`);
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/subscriptions/', payload);
    return data;
  },
  cancel: async (id: number) => {
    const { data } = await api.post(`/subscriptions/${id}/cancel`);
    return data;
  },
  renew: async (id: number) => {
    const { data } = await api.post(`/subscriptions/${id}/renew`);
    return data;
  },
  getMrrDashboard: async () => {
    const { data } = await api.get('/subscriptions/mrr-dashboard');
    return data;
  },
  getRenewals: async (days = 30) => {
    const { data } = await api.get('/subscriptions/renewals', { params: { days } });
    return data;
  },
};

// ── Guided Selling (CPQ Wizard) ──────────────────────
export const guidedSellingApi = {
  list: async () => {
    const { data } = await api.get('/guided-selling/');
    return data;
  },
  get: async (id: number) => {
    const { data } = await api.get(`/guided-selling/${id}`);
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/guided-selling/', payload);
    return data;
  },
  remove: async (id: number) => {
    const { data } = await api.delete(`/guided-selling/${id}`);
    return data;
  },
  evaluate: async (id: number, answers: Record<string, string>) => {
    const { data } = await api.post(`/guided-selling/${id}/evaluate`, { answers });
    return data;
  },
};

// ── Campaigns ────────────────────────────────────────
export const campaignsApi = {
  list: async (params?: { skip?: number; limit?: number; status?: string; type?: string }) => {
    const { data } = await api.get('/campaigns/', { params });
    return data;
  },
  get: async (id: number) => {
    const { data } = await api.get(`/campaigns/${id}`);
    return data;
  },
  create: async (payload: {
    name: string;
    type: string;
    description?: string;
    start_date?: string;
    end_date?: string;
    budget?: number;
  }) => {
    const { data } = await api.post('/campaigns/', payload);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/campaigns/${id}`, payload);
    return data;
  },
  delete: async (id: number) => {
    const { data } = await api.delete(`/campaigns/${id}`);
    return data;
  },
  getRoi: async (id: number) => {
    const { data } = await api.get(`/campaigns/${id}/roi`);
    return data;
  },
  getMembers: async (id: number, params?: { skip?: number; limit?: number }) => {
    const { data } = await api.get(`/campaigns/${id}/members`, { params });
    return data;
  },
  addMembers: async (id: number, members: Array<{ lead_id?: number; customer_id?: number }>) => {
    const { data } = await api.post(`/campaigns/${id}/members`, members);
    return data;
  },
  removeMember: async (campaignId: number, memberId: number) => {
    const { data } = await api.delete(`/campaigns/${campaignId}/members/${memberId}`);
    return data;
  },
  updateMemberStatus: async (campaignId: number, memberId: number, status: string) => {
    const { data } = await api.patch(`/campaigns/${campaignId}/members/${memberId}/status`, {
      status,
    });
    return data;
  },
};

// ── Invoices ─────────────────────────────────────────
export const invoicesApi = {
  list: async (params?: {
    skip?: number;
    limit?: number;
    status?: string;
    customer_id?: number;
  }) => {
    const { data } = await api.get('/invoices/', { params });
    return data;
  },
  get: async (id: number) => {
    const { data } = await api.get(`/invoices/${id}`);
    return data;
  },
  create: async (payload: {
    customer_id: number;
    quote_id?: number;
    contract_id?: number;
    notes?: string;
    items_json?: string;
    tax_rate?: number;
  }) => {
    const { data } = await api.post('/invoices/', payload);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/invoices/${id}`, payload);
    return data;
  },
  updateStatus: async (id: number, status: string) => {
    const { data } = await api.patch(`/invoices/${id}/status`, { status });
    return data;
  },
  createFromQuote: async (quoteId: number) => {
    const { data } = await api.post(`/invoices/from-quote/${quoteId}`);
    return data;
  },
};

// ── E-Signatures ──────────────────────────────────────
export const signaturesApi = {
  request: async (payload: {
    document_type: string;
    document_id: number;
    signer_email: string;
    signer_name?: string;
  }) => {
    const { data } = await api.post('/signatures/request', payload);
    return data;
  },
  list: async () => {
    const { data } = await api.get('/signatures/');
    return data;
  },
  getPublic: async (token: string) => {
    const { data } = await api.get(`/sign/${token}`);
    return data;
  },
  sign: async (token: string, payload: { signature_data?: string; signer_name?: string }) => {
    const { data } = await api.post(`/sign/${token}`, payload);
    return data;
  },
  decline: async (token: string) => {
    const { data } = await api.post(`/sign/${token}/decline`);
    return data;
  },
};

// ── Pipelines ────────────────────────────────────────
export const pipelinesApi = {
  list: async () => {
    const { data } = await api.get('/pipelines/');
    return data;
  },
  get: async (id: number) => {
    const { data } = await api.get(`/pipelines/${id}`);
    return data;
  },
  create: async (payload: {
    name: string;
    stages_json?: string;
    description?: string;
    is_default?: boolean;
  }) => {
    const { data } = await api.post('/pipelines/', payload);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/pipelines/${id}`, payload);
    return data;
  },
  delete: async (id: number) => {
    const { data } = await api.delete(`/pipelines/${id}`);
    return data;
  },
  setDefault: async (id: number) => {
    const { data } = await api.patch(`/pipelines/${id}/set-default`);
    return data;
  },
};

// ── Territories ──────────────────────────────────────
export const territoriesApi = {
  list: async () => {
    const { data } = await api.get('/territories/');
    return data;
  },
  getTree: async () => {
    const { data } = await api.get('/territories/tree');
    return data;
  },
  get: async (id: number) => {
    const { data } = await api.get(`/territories/${id}`);
    return data;
  },
  create: async (payload: {
    name: string;
    parent_id?: number;
    description?: string;
    region?: string;
    rules_json?: string;
  }) => {
    const { data } = await api.post('/territories/', payload);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/territories/${id}`, payload);
    return data;
  },
  delete: async (id: number) => {
    const { data } = await api.delete(`/territories/${id}`);
    return data;
  },
  addAssignment: async (territoryId: number, payload: { user_id: number; role: string }) => {
    const { data } = await api.post(`/territories/${territoryId}/assignments`, payload);
    return data;
  },
  removeAssignment: async (territoryId: number, userId: number) => {
    const { data } = await api.delete(`/territories/${territoryId}/assignments/${userId}`);
    return data;
  },
  autoAssign: async () => {
    const { data } = await api.post('/territories/auto-assign');
    return data;
  },
  getMetrics: async (territoryId: number) => {
    const { data } = await api.get(`/territories/${territoryId}/metrics`);
    return data;
  },
  listOpportunities: async (territoryId: number, params?: { limit?: number; offset?: number }) => {
    const { data } = await api.get(`/territories/${territoryId}/opportunities`, { params });
    return data;
  },
};

// ── Contracts ────────────────────────────────────────
export const contractsApi = {
  list: async (params?: Record<string, unknown>) => {
    const { data } = await api.get('/contracts/', { params });
    return data;
  },
  get: async (id: number) => {
    const { data } = await api.get(`/contracts/${id}`);
    return data;
  },
  create: async (payload: Record<string, unknown>) => {
    const { data } = await api.post('/contracts/', payload);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/contracts/${id}`, payload);
    return data;
  },
  amend: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.post(`/contracts/${id}/amend`, payload);
    return data;
  },
  activate: async (id: number) => {
    const { data } = await api.post(`/contracts/${id}/activate`);
    return data;
  },
  expiring: async (days = 30) => {
    const { data } = await api.get('/contracts/expiring', { params: { days } });
    return data;
  },
};

// ── Revenue Recognition ──────────────────────────────
export const revenueRecApi = {
  listSchedules: async (params?: { contract_id?: number }) => {
    const { data } = await api.get('/revenue-schedules/', { params });
    return data;
  },
  getSchedule: async (id: number) => {
    const { data } = await api.get(`/revenue-schedules/${id}`);
    return data;
  },
  createSchedule: async (payload: {
    contract_id: number;
    recognition_type: string;
    start_date: string;
    end_date: string;
    total_amount: number;
    currency?: string;
  }) => {
    const { data } = await api.post('/revenue-schedules/', payload);
    return data;
  },
  generateEntries: async (id: number) => {
    const { data } = await api.post(`/revenue-schedules/${id}/generate-entries`);
    return data;
  },
  recognizeEntry: async (scheduleId: number, entryId: number) => {
    const { data } = await api.patch(
      `/revenue-schedules/${scheduleId}/entries/${entryId}/recognize`,
    );
    return data;
  },
  getDashboard: async () => {
    const { data } = await api.get('/revenue-recognition/dashboard');
    return data;
  },
};

// ── Chat ─────────────────────────────────────────────
export const chatApi = {
  createSession: async (payload: { visitor_id: string; metadata_json?: string }) => {
    const { data } = await api.post('/chat/sessions', payload);
    return data;
  },
  listSessions: async () => {
    const { data } = await api.get('/chat/sessions/');
    return data;
  },
  assignSession: async (id: number) => {
    const { data } = await api.patch(`/chat/sessions/${id}/assign`);
    return data;
  },
  closeSession: async (id: number) => {
    const { data } = await api.patch(`/chat/sessions/${id}/close`);
    return data;
  },
  getMessages: async (sessionId: number) => {
    const { data } = await api.get(`/chat/sessions/${sessionId}/messages`);
    return data;
  },
  sendMessage: async (
    sessionId: number,
    payload: { content: string; sender_type: string; sender_id?: string },
  ) => {
    const { data } = await api.post(`/chat/sessions/${sessionId}/messages`, payload);
    return data;
  },
};

// ── Stakeholders (Buyer Relationship Map) ──
export const stakeholdersApi = {
  listByOpportunity: async (opportunityId: number) => {
    const { data } = await api.get(`/stakeholders/opportunity/${opportunityId}`);
    return data;
  },
  listByCustomer: async (customerId: number) => {
    const { data } = await api.get(`/stakeholders/customer/${customerId}`);
    return data;
  },
  create: async (payload: {
    opportunity_id?: number;
    customer_id?: number;
    name: string;
    email?: string;
    title?: string;
    phone?: string;
    seniority?: string;
    department_group?: string;
    buyer_role?: string;
    notes?: string;
  }) => {
    const { data } = await api.post('/stakeholders/', payload);
    return data;
  },
  update: async (id: number, payload: Record<string, unknown>) => {
    const { data } = await api.put(`/stakeholders/${id}`, payload);
    return data;
  },
  delete: async (id: number) => {
    await api.delete(`/stakeholders/${id}`);
  },
  getAlerts: async (opportunityId: number) => {
    const { data } = await api.get(`/stakeholders/opportunity/${opportunityId}/alerts`);
    return data;
  },
};

// ── Sequence V2 Analytics ──
export const sequenceV2Api = {
  getEnrollmentDetail: async (enrollmentId: number) => {
    const { data } = await api.get(`/engagement/sequences/enrollments/${enrollmentId}/detail`);
    return data;
  },
  getStepRuns: async (enrollmentId: number) => {
    const { data } = await api.get(`/engagement/sequences/enrollments/${enrollmentId}/step-runs`);
    return data;
  },
  getAnalytics: async () => {
    const { data } = await api.get('/engagement/sequences/analytics');
    return data;
  },
  getPerformance: async () => {
    const { data } = await api.get('/engagement/sequences/performance');
    return data;
  },
  getVariantMetrics: async (sequenceId?: number) => {
    const params = sequenceId ? `?sequence_id=${sequenceId}` : '';
    const { data } = await api.get(`/engagement/sequences/variant-metrics${params}`);
    return data;
  },
  getDomainEvents: async (eventType?: string, limit = 50) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (eventType) params.set('event_type', eventType);
    const { data } = await api.get(`/engagement/sequences/domain-events?${params}`);
    return data;
  },
};

// ── V4 Feature Store ─────────────────────────────────
//
// Per-opportunity daily feature snapshot (momentum, drivers, buyer
// state, etc.). The audit found this endpoint had no client wired up
// at all, so the deal-health card couldn't surface momentum drivers
// even though the backend was computing them nightly.
export interface OpportunityFeatureSnapshot {
  opportunity_id: number;
  snapshot_date: string;
  deal_age_days: number | null;
  days_since_last_rep_touch: number | null;
  days_since_last_buyer_touch: number | null;
  rep_touch_count_14d: number | null;
  buyer_reply_count_14d: number | null;
  meeting_count_30d: number | null;
  quote_count: number | null;
  latest_discount_pct: number | null;
  competitor_mentions_30d: number | null;
  pricing_objections_30d: number | null;
  positive_signal_count_14d: number | null;
  negative_signal_count_14d: number | null;
  momentum_score: number | null;
  momentum_band: 'low' | 'medium' | 'high' | string | null;
  /** Deserialised list of driver objects (label, contribution, weight). */
  momentum_drivers: Array<{
    label?: string;
    contribution?: number;
    weight?: number;
    direction?: 'positive' | 'negative';
    [key: string]: unknown;
  }>;
  buyer_state: string | null;
  close_probability: number | null;
  stage_velocity_days: number | null;
  objection_density_norm: number | null;
}

export const featureStoreApi = {
  getLatest: async (opportunityId: number): Promise<OpportunityFeatureSnapshot | null> => {
    const { data } = await api.get(`/v4/opportunities/${opportunityId}/features/latest`);
    return (data?.data ?? null) as OpportunityFeatureSnapshot | null;
  },
};

// ── V5 Intelligence ──────────────────────────────────
//
// Wraps the entire ``/v5/...`` router. Five separate sub-features
// (similarity, objection patterns, timing windows, rep DNA, network
// anomalies) used to live without any frontend client at all — the
// audit flagged them as the largest unwired surface in the codebase.
//
// Types favour conservative shapes (nullable fields, json-blob-as-
// array fallbacks) because some payloads come from experimental
// V5 services where missing fields are common in practice.

export interface SimilarDealLink {
  related_opportunity_id: number;
  similarity_score: number;
  reason?: string | null;
  related_title?: string | null;
  related_stage?: string | null;
  related_amount?: number | null;
}

export interface ObjectionRecord {
  id: number;
  objection_type: string;
  severity: 'low' | 'med' | 'high' | string;
  evidence_text: string | null;
  resolved_flag: boolean;
  ttr_hours: number | null;
  created_at: string | null;
}

export interface TimingWindow {
  id: number;
  action_type: string;
  window_start: string | null;
  window_end: string | null;
  urgency_score: number | null;
  reason_codes: string[];
  status: string;
}

export interface RepDnaProfile {
  cluster_label: string | null;
  strengths: Array<{ label?: string; score?: number; [k: string]: unknown }>;
  gaps: Array<{ label?: string; score?: number; [k: string]: unknown }>;
  metrics: Record<string, unknown> | null;
  sample_period_start: string | null;
  sample_period_end: string | null;
  generated_at: string | null;
}

export interface NetworkAnomaly {
  id: number;
  segment_key: string;
  metric_name: string;
  expected_value: number | null;
  actual_value: number | null;
  z_score: number | null;
  severity: string;
  explanation: unknown;
  detected_at: string | null;
}

// ── Public Config (feature flags) ───────────────────
//
// Returns the live feature-flag state for the running deployment so
// the frontend can hide routes, sidebar entries, and dashboards that
// depend on flags currently disabled. Backend allow-lists which
// flags are exposed (see app/api/v1/config.py); secrets and DB URLs
// are intentionally never returned.

export interface FeatureFlagsResponse {
  env: string;
  release: string;
  flags: Record<string, boolean>;
}

export const configApi = {
  getFeatureFlags: async (): Promise<FeatureFlagsResponse> => {
    const { data } = await api.get<FeatureFlagsResponse>('/config/feature-flags');
    return data;
  },
};

export const v5IntelligenceApi = {
  getSimilar: async (opportunityId: number, limit = 5) => {
    const { data } = await api.get(`/v5/opportunities/${opportunityId}/similar`, {
      params: { limit },
    });
    return data as { opportunity_id: number; items: SimilarDealLink[]; total: number };
  },
  getObjections: async (opportunityId: number) => {
    const { data } = await api.get(`/v5/opportunities/${opportunityId}/objections`);
    return data as { opportunity_id: number; items: ObjectionRecord[]; total: number };
  },
  detectObjections: async (opportunityId: number) => {
    const { data } = await api.post(`/v5/opportunities/${opportunityId}/objections/detect`);
    return data;
  },
  resolveObjection: async (objectionId: number, payload: Record<string, unknown>) => {
    const { data } = await api.post(`/v5/objections/${objectionId}/resolution`, payload);
    return data;
  },
  getTimingWindows: async (opportunityId: number) => {
    const { data } = await api.get(`/v5/opportunities/${opportunityId}/timing-windows`);
    return data as { opportunity_id: number; items: TimingWindow[]; total: number };
  },
  markTimingWindowDone: async (opportunityId: number, windowId: number) => {
    const { data } = await api.post(
      `/v5/opportunities/${opportunityId}/timing-windows/${windowId}/done`,
    );
    return data;
  },
  getDnaRecommendations: async (segmentKey: string, limit = 10) => {
    const { data } = await api.get(
      `/v5/segments/${encodeURIComponent(segmentKey)}/dna-recommendations`,
      {
        params: { limit },
      },
    );
    return data as { segment_key: string; items: unknown[]; total: number };
  },
  getRecentNetworkAnomalies: async (limit = 50) => {
    const { data } = await api.get(`/v5/network/anomalies/recent`, { params: { limit } });
    return data as { items: NetworkAnomaly[]; total: number };
  },
  getRepDna: async (repId: number) => {
    const { data } = await api.get(`/v5/reps/${repId}/dna`);
    return data as { rep_id: number; profile: RepDnaProfile | null };
  },
};

export default api;
