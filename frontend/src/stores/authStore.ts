import { create } from 'zustand';
import type { AxiosError } from 'axios';

import type { User } from '../lib/types';
import { authApi } from '../lib/api';
import { queryClient } from '../lib/queryClient';
import { storage } from '../lib/storage';

const COOKIE_AUTH_ONLY = import.meta.env.VITE_COOKIE_AUTH_ONLY === 'true';

interface ApiErrorResponse {
  error?: { message?: string };
  detail?: string | Array<{ msg?: string }>;
  message?: string;
}

const LOGIN_ERROR_MESSAGES: Record<number, string> = {
  401: 'E-posta veya sifre hatali',
  403: 'Hesabiniz devre disi birakilmis',
  404: 'Kullanıcı bulunamadi',
  429: 'Çok fazla deneme yaptiniz, lütfen bekleyin',
};

function extractLoginErrorMessage(error: unknown): string {
  const axiosError = error as AxiosError<ApiErrorResponse>;

  if (!axiosError.response) {
    return 'Sunucuya baglanilamiyor, internet baglantinizi kontrol edin';
  }

  const { status, data } = axiosError.response;

  const serverMessage =
    data?.error?.message ||
    (typeof data?.detail === 'string' ? data.detail : undefined) ||
    data?.message;

  if (serverMessage) {
    return serverMessage;
  }

  return LOGIN_ERROR_MESSAGES[status] || 'Giris başarısız, lütfen tekrar deneyin';
}

interface AuthState {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  bootstrap: () => Promise<void>;
  clearError: () => void;
  setAuth: (token: string, refreshToken: string, user: User) => void;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  user: storage.get<User | null>('user', null),
  token: COOKIE_AUTH_ONLY ? null : localStorage.getItem('token'),
  refreshToken: COOKIE_AUTH_ONLY ? null : localStorage.getItem('refreshToken'),
  isAuthenticated: COOKIE_AUTH_ONLY ? false : !!localStorage.getItem('token'),
  isLoading: false,
  error: null,

  login: async (email: string, password: string) => {
    set({ isLoading: true, error: null });
    try {
      const response = await authApi.login(email, password);
      const { access_token, refresh_token, user } = response;

      if (!COOKIE_AUTH_ONLY) {
        localStorage.setItem('token', access_token);
        localStorage.setItem('refreshToken', refresh_token);
      } else {
        localStorage.removeItem('token');
        localStorage.removeItem('refreshToken');
      }
      storage.set('user', user);

      set({
        token: COOKIE_AUTH_ONLY ? null : access_token,
        refreshToken: COOKIE_AUTH_ONLY ? null : refresh_token,
        user,
        isAuthenticated: true,
      });
    } catch (e) {
      const message = extractLoginErrorMessage(e);
      set({ error: message });
      throw e;
    } finally {
      set({ isLoading: false });
    }
  },

  bootstrap: async () => {
    // Cookie-first bootstrap: if cookies exist, /auth/me will succeed even without localStorage.
    set({ isLoading: true, error: null });
    try {
      const me = await authApi.getMe();
      storage.set('user', me);
      set({
        user: me,
        isAuthenticated: true,
        // keep token fields as-is; cookie-only mode doesn't use them
      });
    } catch {
      // Not authenticated (or backend down) → clear local state
      localStorage.removeItem('token');
      localStorage.removeItem('refreshToken');
      storage.remove('user');
      set({
        token: null,
        refreshToken: null,
        user: null,
        isAuthenticated: false,
      });
    } finally {
      set({ isLoading: false });
    }
  },

  logout: async () => {
    const { refreshToken } = get();
    try {
      await authApi.logout(COOKIE_AUTH_ONLY ? null : refreshToken);
    } catch {
      // Ignore logout API errors – clear local state regardless
    }

    localStorage.removeItem('token');
    localStorage.removeItem('refreshToken');
    storage.remove('user');

    // R5-CACHE-1 — wipe TanStack cache so the next user on this
    // browser tab cannot see the previous user's PII for the
    // 30s staleTime window.
    queryClient.clear();

    set({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
    });
  },

  clearError: () => set({ error: null }),

  setAuth: (token: string, refreshToken: string, user: User) => {
    if (!COOKIE_AUTH_ONLY) {
      localStorage.setItem('token', token);
      localStorage.setItem('refreshToken', refreshToken);
    }
    storage.set('user', user);

    set({
      token: COOKIE_AUTH_ONLY ? null : token,
      refreshToken: COOKIE_AUTH_ONLY ? null : refreshToken,
      user,
      isAuthenticated: true,
    });
  },
}));
