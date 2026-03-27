import axios from 'axios';
import { toast } from 'sonner';
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
} from './types';

// ── Axios instance ───────────────────────────────────
const BACKEND_URL = import.meta.env.VITE_API_URL || '/api/v1';

const api = axios.create({
  baseURL: BACKEND_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Request interceptor – attach JWT
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor – handle errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (!error.response) {
      toast.error('Baglanti hatasi');
      return Promise.reject(error);
    }

    const { status, data } = error.response;

    if (status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('refreshToken');
      localStorage.removeItem('user');
      window.location.href = '/login';
    } else if (status === 403) {
      toast.error('Bu isleme yetkiniz yok');
    } else if (status === 422) {
      const detail = data?.detail;
      if (Array.isArray(detail)) {
        const messages = detail.map(
          (err: { loc?: string[]; msg?: string }) =>
            err.msg || JSON.stringify(err),
        );
        toast.error(messages.join(', '));
      } else if (typeof detail === 'string') {
        toast.error(detail);
      } else {
        toast.error('Gecersiz veri');
      }
    } else if (status >= 500) {
      toast.error('Sunucu hatasi, lutfen tekrar deneyin');
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

  refresh: async (refreshToken: string): Promise<TokenResponse> => {
    const { data } = await api.post<TokenResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    return data;
  },

  logout: async (refreshToken: string): Promise<void> => {
    await api.post('/auth/logout', { refresh_token: refreshToken });
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
    const { data } = await api.get<PaginatedResponse<EmailRequest>>('/emails', { params });
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

  reparseEmail: async (id: number): Promise<EmailRequest> => {
    const { data } = await api.post<EmailRequest>(`/emails/${id}/reparse`);
    return data;
  },

  getEmailMatches: async (id: number): Promise<MatchResult[]> => {
    const { data } = await api.get<MatchResult[]>(`/emails/${id}/matches`);
    return data;
  },

  reviewEmail: async (id: number, action: string): Promise<EmailRequest> => {
    const { data } = await api.post<EmailRequest>(`/emails/${id}/review`, { action });
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
    const { data } = await api.post<SparePart>('/parts', payload);
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
    const { data } = await api.get<PaginatedResponse<PriceEntry>>('/prices', { params });
    return data;
  },

  createPrice: async (payload: Partial<PriceEntry>): Promise<PriceEntry> => {
    const { data } = await api.post<PriceEntry>('/prices', payload);
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
    const { data } = await api.get<PaginatedResponse<Customer>>('/customers', { params });
    return data;
  },

  getCustomer: async (id: number): Promise<Customer> => {
    const { data } = await api.get<Customer>(`/customers/${id}`);
    return data;
  },

  createCustomer: async (payload: Partial<Customer>): Promise<Customer> => {
    const { data } = await api.post<Customer>('/customers', payload);
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
};

// ── Quotes ───────────────────────────────────────────
export const quotesApi = {
  getQuotes: async (params?: Record<string, unknown>): Promise<PaginatedResponse<Quote>> => {
    const { data } = await api.get<PaginatedResponse<Quote>>('/quotes', { params });
    return data;
  },

  getQuote: async (id: number): Promise<Quote> => {
    const { data } = await api.get<Quote>(`/quotes/${id}`);
    return data;
  },

  createQuote: async (payload: Record<string, unknown>): Promise<Quote> => {
    const { data } = await api.post<Quote>('/quotes', payload);
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
    const { data } = await api.post<Quote>(`/quotes/${id}/approve`);
    return data;
  },

  sendQuote: async (id: number): Promise<Quote> => {
    const { data } = await api.post<Quote>(`/quotes/${id}/send`);
    return data;
  },

  getQuotePdfUrl: (id: number): string => {
    return `/api/v1/quotes/${id}/pdf`;
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
};

// ── Settings ─────────────────────────────────────────
export const settingsApi = {
  getSettings: async (): Promise<Record<string, unknown>> => {
    const { data } = await api.get<Record<string, unknown>>('/settings');
    return data;
  },

  updateSettings: async (payload: Record<string, unknown>): Promise<Record<string, unknown>> => {
    const { data } = await api.put<Record<string, unknown>>('/settings', payload);
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
};

export default api;
