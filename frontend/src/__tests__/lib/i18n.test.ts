import { describe, it, expect } from 'vitest';
import { t } from '../../lib/i18n';

describe('i18n translation', () => {
  it('returns Turkish by default', () => {
    expect(t('nav.home')).toBe('Ana Sayfa');
    expect(t('nav.settings')).toBe('Ayarlar');
  });

  it('returns English translations', () => {
    expect(t('nav.home', 'en')).toBe('Dashboard');
    expect(t('nav.settings', 'en')).toBe('Settings');
  });

  it('returns German translations', () => {
    expect(t('nav.home', 'de')).toBe('Startseite');
  });

  it('returns French translations', () => {
    expect(t('nav.home', 'fr')).toBe('Accueil');
  });

  it('returns Spanish translations', () => {
    expect(t('nav.home', 'es')).toBe('Inicio');
  });

  it('falls back to Turkish for unknown language', () => {
    expect(t('nav.home', 'xx')).toBe('Ana Sayfa');
  });

  it('returns key for unknown translation key', () => {
    expect(t('unknown.key' as Parameters<typeof t>[0])).toBe('unknown.key');
  });
});
