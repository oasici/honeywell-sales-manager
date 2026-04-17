import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ResponsiveContainer } from 'recharts';

interface SafeChartProps {
  height?: number;
  minHeight?: number;
  children: ReactNode;
}

/**
 * Wraps Recharts ResponsiveContainer to prevent the "width(-1) and height(-1)"
 * error that happens when the parent hasn't been measured yet (e.g. hidden
 * tabs, just-mounted lazy routes, flex containers without explicit size).
 *
 * Uses ResizeObserver to only render the chart once the parent has a real
 * width. If ResizeObserver is unavailable, falls back to a short timeout.
 */
export function SafeChart({ height = 300, minHeight = 200, children }: SafeChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    if (typeof ResizeObserver === 'undefined') {
      const id = window.setTimeout(() => setReady(true), 80);
      return () => window.clearTimeout(id);
    }

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect.width > 0) {
          setReady(true);
          observer.disconnect();
          return;
        }
      }
    });
    observer.observe(el);

    // Fallback in case ResizeObserver is slow on first mount
    const fallback = window.setTimeout(() => setReady(true), 300);

    return () => {
      observer.disconnect();
      window.clearTimeout(fallback);
    };
  }, []);

  return (
    <div ref={containerRef} style={{ width: '100%', height, minHeight }}>
      {ready ? (
        <ResponsiveContainer width="100%" height="100%">
          {children as React.ReactElement}
        </ResponsiveContainer>
      ) : null}
    </div>
  );
}
