import { Link } from 'react-router-dom';

export interface AiSummarySource {
  type: string;
  id: number;
  label: string;
}

/** Normalizes API sources (structured dicts or legacy strings). */
export function normalizeAiSources(raw: unknown): AiSummarySource[] {
  if (!Array.isArray(raw)) return [];
  const out: AiSummarySource[] = [];
  for (const item of raw) {
    if (typeof item === 'string') {
      out.push({ type: 'text', id: 0, label: item });
      continue;
    }
    if (item && typeof item === 'object') {
      const o = item as Record<string, unknown>;
      out.push({
        type: String(o.type ?? 'text'),
        id: typeof o.id === 'number' ? o.id : Number(o.id) || 0,
        label: String(o.label ?? ''),
      });
    }
  }
  return out;
}

function hrefForSource(s: AiSummarySource): string | null {
  if (!s.id) return null;
  switch (s.type) {
    case 'quote':
      return `/quotes/${s.id}`;
    case 'email':
      return `/emails/${s.id}`;
    case 'opportunity':
      return `/opportunities/${s.id}`;
    case 'customer':
      return `/customers/${s.id}`;
    default:
      return null;
  }
}

export function SummarySourceLinks({
  sources,
  className = '',
}: {
  sources: unknown;
  className?: string;
}) {
  const list = normalizeAiSources(sources).filter((s) => s.label || s.type !== 'text');
  if (list.length === 0) return null;

  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      {list.map((s, idx) => {
        const to = hrefForSource(s);
        const key = `${s.type}-${s.id}-${idx}`;
        if (!to || s.type === 'text') {
          return (
            <span
              key={key}
              className="inline-flex max-w-[220px] truncate rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
              title={s.label}
            >
              {s.label || s.type}
            </span>
          );
        }
        return (
          <Link
            key={key}
            to={to}
            className="inline-flex max-w-[220px] truncate rounded-md border border-honeywell-red/30 bg-honeywell-red/5 px-2 py-1 text-xs font-medium text-honeywell-red hover:bg-honeywell-red/10 dark:border-honeywell-red/40"
            title={s.label}
          >
            {s.label || `${s.type} #${s.id}`}
          </Link>
        );
      })}
    </div>
  );
}
