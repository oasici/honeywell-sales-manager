import { create } from 'zustand';

type Theme = 'light' | 'dark';
type Language = 'tr' | 'en' | 'de' | 'fr' | 'es';

interface PreferencesState {
  theme: Theme;
  language: Language;
  fontSizeOffset: number; // -4 to +4
  setTheme: (theme: Theme) => void;
  setLanguage: (language: Language) => void;
  setFontSizeOffset: (offset: number) => void;
}

const STORAGE_KEY = 'honeywell-preferences';

function loadPreferences(): { theme: Theme; language: Language; fontSizeOffset: number } {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored);
      return {
        theme: parsed.theme || 'light',
        language: parsed.language || 'tr',
        fontSizeOffset: parsed.fontSizeOffset ?? 0,
      };
    }
  } catch { /* ignore */ }
  return { theme: 'light', language: 'tr', fontSizeOffset: 0 };
}

function savePreferences(state: { theme: Theme; language: Language; fontSizeOffset: number }) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function applyTheme(theme: Theme) {
  if (theme === 'dark') {
    document.documentElement.classList.add('dark');
  } else {
    document.documentElement.classList.remove('dark');
  }
}

function applyFontSize(offset: number) {
  document.documentElement.style.setProperty('--font-size-offset', `${offset}px`);
  const root = document.getElementById('root');
  if (root) {
    if (offset !== 0) {
      root.classList.add('font-scaled');
    } else {
      root.classList.remove('font-scaled');
    }
  }
}

const initial = loadPreferences();
applyTheme(initial.theme);
applyFontSize(initial.fontSizeOffset);

export const usePreferencesStore = create<PreferencesState>((set) => ({
  theme: initial.theme,
  language: initial.language,
  fontSizeOffset: initial.fontSizeOffset,

  setTheme: (theme) => {
    applyTheme(theme);
    set((state) => {
      const next = { ...state, theme };
      savePreferences(next);
      return next;
    });
  },

  setLanguage: (language) => {
    set((state) => {
      const next = { ...state, language };
      savePreferences(next);
      return next;
    });
  },

  setFontSizeOffset: (fontSizeOffset) => {
    const clamped = Math.max(-4, Math.min(4, fontSizeOffset));
    applyFontSize(clamped);
    set((state) => {
      const next = { ...state, fontSizeOffset: clamped };
      savePreferences(next);
      return next;
    });
  },
}));
