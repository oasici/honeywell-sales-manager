interface SkeletonProps {
  variant?: 'line' | 'card' | 'table';
  count?: number;
  className?: string;
}

function SkeletonLine() {
  return <div className="h-4 w-full animate-pulse rounded bg-gray-200" />;
}

function SkeletonCard() {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="mb-4 h-4 w-1/3 animate-pulse rounded bg-gray-200" />
      <div className="space-y-3">
        <div className="h-3 w-full animate-pulse rounded bg-gray-200" />
        <div className="h-3 w-5/6 animate-pulse rounded bg-gray-200" />
        <div className="h-3 w-4/6 animate-pulse rounded bg-gray-200" />
      </div>
    </div>
  );
}

function SkeletonTable() {
  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 bg-white">
      {/* Header */}
      <div className="flex gap-4 border-b border-gray-200 bg-gray-50 px-6 py-3">
        <div className="h-3 w-1/4 animate-pulse rounded bg-gray-300" />
        <div className="h-3 w-1/4 animate-pulse rounded bg-gray-300" />
        <div className="h-3 w-1/4 animate-pulse rounded bg-gray-300" />
        <div className="h-3 w-1/4 animate-pulse rounded bg-gray-300" />
      </div>
      {/* Rows */}
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          className="flex gap-4 border-b border-gray-100 px-6 py-4 last:border-b-0"
        >
          <div className="h-3 w-1/4 animate-pulse rounded bg-gray-200" />
          <div className="h-3 w-1/4 animate-pulse rounded bg-gray-200" />
          <div className="h-3 w-1/4 animate-pulse rounded bg-gray-200" />
          <div className="h-3 w-1/4 animate-pulse rounded bg-gray-200" />
        </div>
      ))}
    </div>
  );
}

export function Skeleton({ variant = 'line', count = 1, className }: SkeletonProps) {
  if (className) {
    return <div className={`animate-pulse bg-gray-200 ${className}`} />;
  }
  const items = Array.from({ length: count }, (_, i) => i);

  if (variant === 'card') {
    return (
      <div className="space-y-4">
        {items.map((i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  if (variant === 'table') {
    return (
      <div className="space-y-4">
        {items.map((i) => (
          <SkeletonTable key={i} />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((i) => (
        <SkeletonLine key={i} />
      ))}
    </div>
  );
}
