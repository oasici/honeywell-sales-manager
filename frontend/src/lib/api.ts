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
  // Guard against redirect loop: don't redirect if already on login
  if (!window.location.pathname.startsWith('/login')) {
    window.location.href = '/login';
  }
};

// Response interceptor – handle errors
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    if (!error.response) {
      toast.error('Baglanti hatasi');
      return Promise.reject(error);
    }

    const { status, data } = error.response;
    const originalRequest = error.config;

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
      toast.error(tt('errors.api_forbidden'));
    } else if (status === 422) {
      const detail = data?.detail;
      if (Array.isArray(detail)) {
        const messages = detail.map(
          (err: { loc?: string[]; msg?: string }) => err.msg || JSON.stringify(err),
        );
        toast.error(messages.join(', '));
      } else if (typeof detail === 'string') {
        toast.error(detail);
      } else {
        toast.error(tt('errors.api_invalid_data'));
      }
    } else if (status >= 500) {
      toast.error(tt('errors.api_server_error'));
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
};

// ── Parts ────────────────────────────────────────────
export const partsApi = {
  getParts: async (params?: Record<string, unknown>): Promise<PaginatedResponse<SparePart>> => {
    const { data } = await api.get<PaginatedResponse<SparePart>>('/parts/', { params });
    return data;
  },

  getCategories: async (): Promise<string[]> => {
    const { data } = await api.get<string[]>('/parts/categories');
    return data;
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
      const blob = new Blob([data], { type: headers['content-type'] || 'application/pdf' });
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
  getNotifications: async (unreadOnly = false, limit = 20) => {
    const { data } = await api.get('/notifications/', {
      params: { unread_only: unreadOnly, limit },
    });
    return data;
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
  summarize: async (payload: { entity_type: string; entity_id: number; focus?: string }) => {
    const { data } = await api.post('/ai/summarize', payload);
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

export default api;
