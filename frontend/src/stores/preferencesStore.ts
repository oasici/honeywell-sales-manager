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

// Round-11 R11-FE-3 — SSR guard. The store is initialised at module
// load time, before any React tree exists; on a Node-side render
// `localStorage` and `document` are undefined and would throw, which
// would block first-paint hydration. Guarding lets the same module
// boot cleanly on the server (where preferences are just defaults).
const HAS_DOM = typeof document !== 'undefined';
const HAS_STORAGE = typeof localStorage !== 'undefined';

function loadPreferences(): { theme: Theme; language: Language; fontSizeOffset: number } {
  if (!HAS_STORAGE) {
    return { theme: 'light', language: 'tr', fontSizeOffset: 0 };
  }
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
  if (!HAS_STORAGE) return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

function applyTheme(theme: Theme) {
  if (!HAS_DOM) return;
  if (theme === 'dark') {
    document.documentElement.classList.add('dark');
  } else {
    document.documentElement.classList.remove('dark');
  }
}

function applyFontSize(offset: number) {
  if (!HAS_DOM) return;
  const root = document.getElementById('root');
  if (!root) return;
  // Remove all previous scale classes
  root.className = root.className.replace(/font-scale-\S+/g, '').trim();
  // Add appropriate class
  if (offset > 0) {
    root.classList.add(`font-scale-up-${Math.min(offset, 4)}`);
  } else if (offset < 0) {
    root.classList.add(`font-scale-down-${Math.min(Math.abs(offset), 4)}`);
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
