import { usePreferencesStore } from '../stores/preferencesStore';
import { t, type TranslationKey } from '../lib/i18n';

export function useT() {
  const language = usePreferencesStore((s) => s.language);
  return (key: TranslationKey) => t(key, language);
}
