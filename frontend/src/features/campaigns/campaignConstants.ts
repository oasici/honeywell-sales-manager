export const STATUS_LABELS: Record<string, string> = {
  draft: 'Taslak',
  active: 'Aktif',
  paused: 'Durduruldu',
  completed: 'Tamamlandi',
};

export const STATUS_VARIANTS: Record<
  string,
  'default' | 'info' | 'warning' | 'success' | 'danger'
> = {
  draft: 'default',
  active: 'success',
  paused: 'warning',
  completed: 'info',
};
