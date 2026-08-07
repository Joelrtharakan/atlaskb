// Shared formatting helpers. Dates/timestamps are system facts → rendered in
// mono at the call site; these just produce the strings.

export function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** Compact fixed-precision for relevance scores in the mono margin. */
export function formatScore(n: number | null): string {
  if (n == null) return "—";
  return n.toFixed(4);
}
