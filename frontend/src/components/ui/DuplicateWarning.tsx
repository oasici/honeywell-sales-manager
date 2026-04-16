import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import { duplicatesApi } from '../../lib/api';

interface DuplicateMatch {
  id: number;
  name: string;
  company: string;
  email: string;
  similarity: number;
}

interface DuplicateWarningProps {
  entityType: string;
  name: string;
  company?: string;
  email?: string;
  excludeId?: number;
}

const MIN_CHARS = 3;
const DEBOUNCE_MS = 500;

export function DuplicateWarning({
  entityType,
  name,
  company,
  email,
  excludeId,
}: DuplicateWarningProps) {
  const [matches, setMatches] = useState<DuplicateMatch[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    if (!name || name.trim().length < MIN_CHARS) {
      setMatches([]);
      return;
    }

    timerRef.current = setTimeout(async () => {
      setIsLoading(true);
      try {
        const result = await duplicatesApi.check({
          entity_type: entityType,
          name: name.trim(),
          company: company || undefined,
          email: email || undefined,
          exclude_id: excludeId,
        });
        setMatches(result.data || []);
      } catch {
        setMatches([]);
      } finally {
        setIsLoading(false);
      }
    }, DEBOUNCE_MS);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [entityType, name, company, email, excludeId]);

  if (isLoading) {
    return null;
  }

  if (matches.length === 0) {
    return null;
  }

  const detailPath = entityType === 'customer' ? '/customers' : '/leads';

  return (
    <div className="rounded-lg border border-amber-300 bg-amber-50 p-4">
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="h-5 w-5 text-amber-600 shrink-0" />
        <h4 className="text-sm font-semibold text-amber-800">
          Olasi kopya kayitlar bulundu
        </h4>
      </div>
      <ul className="space-y-2">
        {matches.map((match) => (
          <li key={match.id} className="flex items-center justify-between gap-3">
            <Link
              to={`${detailPath}/${match.id}`}
              className="flex-1 min-w-0 text-sm text-amber-900 hover:underline truncate"
              target="_blank"
              rel="noopener noreferrer"
            >
              <span className="font-medium">{match.name}</span>
              {match.company && (
                <span className="text-amber-700"> - {match.company}</span>
              )}
              {match.email && (
                <span className="text-amber-600 text-xs ml-1">({match.email})</span>
              )}
            </Link>
            <span className="shrink-0 inline-flex items-center rounded-full bg-amber-200 px-2 py-0.5 text-xs font-bold text-amber-900">
              %{Math.round(match.similarity * 100)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
