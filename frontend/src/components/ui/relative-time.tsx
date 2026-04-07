import { useEffect, useState } from "react";
import { formatRelativeDate } from "@/lib/utils";

interface RelativeTimeProps {
  iso: string | null | undefined;
  /** How often to refresh, in milliseconds. Defaults to 30 s. */
  intervalMs?: number;
  className?: string;
}

/**
 * Renders a relative timestamp (e.g. "5m ago") that re-evaluates itself
 * on a timer so it stays accurate without a full page refresh.
 */
export function RelativeTime({
  iso,
  intervalMs = 30_000,
  className,
}: RelativeTimeProps) {
  const [, setTick] = useState(0);
  const label = formatRelativeDate(iso);

  useEffect(() => {
    const id = setInterval(() => setTick((value) => value + 1), intervalMs);
    return () => clearInterval(id);
  }, [intervalMs]);

  return (
    <time
      dateTime={iso ?? undefined}
      title={iso ? new Date(iso).toLocaleString() : undefined}
      className={className}
    >
      {label}
    </time>
  );
}
