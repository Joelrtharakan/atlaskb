import type { DocumentStatus } from "@/lib/types";

import { ContourProgress } from "./ContourProgress";

// Quiet status marker for the document register. No reserved state colors — the
// archive surfaces stay still (design plan §6). Status reads as mono marginalia.

export function StatusBadge({ status }: { status: DocumentStatus }) {
  if (status === "processing") {
    return (
      <span className="inline-flex items-center gap-2 font-mono text-xs text-graphite">
        <ContourProgress size={16} label="Processing" />
        surveying…
      </span>
    );
  }

  if (status === "ready") {
    return (
      <span className="inline-flex items-center gap-2 font-mono text-xs text-ink">
        <span aria-hidden className="h-2 w-2 rounded-full bg-ink" />
        ready
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-2 font-mono text-xs text-ink">
      <span aria-hidden className="h-2 w-2 border border-ink" />
      failed
    </span>
  );
}
