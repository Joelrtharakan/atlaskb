import type { ReactNode } from "react";

// Empty states are invitations, not blank space. A faint contour glyph, a plain
// line of copy, and (optionally) the next action.

export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-4 px-6 py-16 text-center">
      <svg viewBox="0 0 60 60" width="56" height="56" aria-hidden className="text-pewter/60">
        {[6, 12, 18, 24].map((r) => (
          <circle key={r} cx="30" cy="30" r={r} fill="none" stroke="currentColor" strokeWidth="1" />
        ))}
        <circle cx="30" cy="30" r="2" fill="currentColor" />
      </svg>
      <p className="max-w-sm text-sm text-graphite">
        <span className="text-ink">{title}</span>
        {children ? <> {children}</> : null}
      </p>
      {action}
    </div>
  );
}
