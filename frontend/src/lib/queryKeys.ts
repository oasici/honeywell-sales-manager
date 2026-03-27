export const queryKeys = {
  dashboard: { stats: ['dashboard-stats'] as const },
  emails: {
    all: ['emails'] as const,
    list: (filters: Record<string, unknown>) => ['emails', 'list', filters] as const,
    detail: (id: number) => ['emails', 'detail', id] as const,
    matches: (id: number) => ['emails', 'matches', id] as const,
  },
  parts: {
    all: ['parts'] as const,
    list: (filters: Record<string, unknown>) => ['parts', 'list', filters] as const,
    categories: ['parts-categories'] as const,
  },
  quotes: {
    all: ['quotes'] as const,
    list: (filters: Record<string, unknown>) => ['quotes', 'list', filters] as const,
    detail: (id: number) => ['quotes', 'detail', id] as const,
  },
  customers: {
    all: ['customers'] as const,
    list: (filters: Record<string, unknown>) => ['customers', 'list', filters] as const,
    detail: (id: number) => ['customers', 'detail', id] as const,
  },
  analytics: {
    topParts: (days: number) => ['top-parts', days] as const,
    monthlyTrend: (months: number) => ['monthly-trend', months] as const,
  },
  settings: ['settings'] as const,
};
