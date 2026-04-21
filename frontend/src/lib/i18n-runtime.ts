import { t, type TranslationKey } from './i18n';
import { usePreferencesStore } from '../stores/preferencesStore';

/** Translation helper for non-React code (e.g. axios interceptors). Uses current UI language from the preferences store. */
export function tt(key: TranslationKey): string {
  return t(key, usePreferencesStore.getState().language);
}
