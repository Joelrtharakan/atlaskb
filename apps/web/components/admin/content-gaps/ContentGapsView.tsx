"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError, api } from "@/lib/api";
import type { ContentGap, GapCause, ReliefCell } from "@/lib/types";

/** Human-readable label per cause (Trust Layer Phase 7) — the raw enum
 * value is still shown in the marginalia below it for anyone cross-
 * referencing eval/results or server logs. */
const CAUSE_LABELS: Record<GapCause, string> = {
  MISSING_DOCUMENT: "No document covers this",
  OUTDATED_DOCUMENT: "Closest source is stale",
  CONFLICTING_DOCUMENT: "Sources disagree",
  INSUFFICIENT_EVIDENCE: "Weak match only",
  RETRIEVAL_FAILURE: "Content exists, wasn't surfaced",
  PERMISSION_RESTRICTION: "Restricted by ACL",
  MODEL_FAILURE: "Evidence exists, answer still failed",
  AMBIGUOUS_QUERY: "Question too vague to route",
  UNCLASSIFIED: "Not yet classified",
};

const FogOfWar = dynamic(
  () => import("./FogOfWar").then((m) => m.FogOfWar),
  { ssr: false, loading: () => <div className="h-full w-full animate-pulse bg-ink/5" aria-hidden /> },
);

export function ContentGapsView() {
  const [cells, setCells] = useState<ReliefCell[]>([]);
  const [gaps, setGaps] = useState<ContentGap[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resolving, setResolving] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [relief, gapResp] = await Promise.all([api.relief(), api.contentGaps()]);
      setCells(relief.cells);
      setGaps(gapResp.gaps);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't load content gaps.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const resolve = useCallback(async (key: string) => {
    setResolving(key);
    // Optimistic: flip resolved so the fog starts clearing immediately.
    setGaps((prev) => prev?.map((g) => (g.key === key ? { ...g, resolved: true } : g)) ?? prev);
    try {
      const resp = await api.resolveGap(key);
      setGaps(resp.gaps);
    } catch {
      // Roll back on failure.
      setGaps((prev) => prev?.map((g) => (g.key === key ? { ...g, resolved: false } : g)) ?? prev);
    } finally {
      setResolving(null);
    }
  }, []);

  const open = (gaps ?? []).filter((g) => !g.resolved);

  return (
    <section className="mx-auto flex min-h-full max-w-5xl flex-col gap-6 p-4 sm:p-8">
      <header>
        <p className="font-mono text-xs uppercase tracking-cartouche text-graphite">
          Northwind Survey
        </p>
        <h1 className="font-display text-3xl font-medium text-ink">Content gaps</h1>
        <p className="mt-1 text-sm text-graphite">
          Fog marks regions of the atlas where questions went unanswered. Clear a gap once the
          documents cover it — the fog lifts.
        </p>
      </header>

      {error && (
        <p className="border border-graphite/30 bg-linen/50 px-4 py-3 text-sm text-graphite">
          {error}
        </p>
      )}

      <div className="shrink-0 overflow-hidden rounded-lg border border-graphite/25 bg-ink/[0.03]">
        <div className="h-[340px] w-full">
          {gaps ? (
            <FogOfWar cells={cells} gaps={gaps} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-graphite">
              Surveying the fog…
            </div>
          )}
        </div>
        <div className="border-t border-graphite/20 px-4 py-2 font-mono text-xs text-graphite">
          {gaps ? `${open.length} unresolved of ${gaps.length} gaps` : "…"}
        </div>
      </div>

      <div>
        <h2 className="font-display text-lg text-ink">Unanswered questions</h2>
        {gaps && open.length === 0 ? (
          <EmptyState title="No open gaps">The atlas has no fog right now.</EmptyState>
        ) : (
          <ul className="mt-2 divide-y divide-graphite/15">
            {(gaps ?? [])
              .slice()
              .sort((a, b) => Number(a.resolved) - Number(b.resolved) || b.count - a.count)
              .map((g) => (
                <li key={g.key} className="flex items-center justify-between gap-4 py-3">
                  <span className="min-w-0">
                    <span
                      className={`block truncate text-sm ${g.resolved ? "text-graphite line-through" : "text-ink"}`}
                    >
                      {g.query}
                    </span>
                    <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5">
                      <span className="font-mono text-[10px] text-graphite">asked {g.count}×</span>
                      <span className="rounded-sm border border-brass/50 bg-brass/10 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-cartouche text-brass">
                        {CAUSE_LABELS[g.cause] ?? g.cause}
                      </span>
                    </span>
                    {!g.resolved && g.suggested_remediation ? (
                      <span className="mt-1 block max-w-md text-xs text-graphite">
                        {g.suggested_remediation}
                      </span>
                    ) : null}
                  </span>
                  {g.resolved ? (
                    <span className="shrink-0 font-mono text-[10px] uppercase text-graphite">
                      cleared
                    </span>
                  ) : (
                    <button
                      onClick={() => resolve(g.key)}
                      disabled={resolving === g.key}
                      className="shrink-0 border border-graphite/40 px-3 py-1 text-xs text-ink hover:border-pewter disabled:opacity-50"
                    >
                      {resolving === g.key ? "Clearing…" : "Resolve"}
                    </button>
                  )}
                </li>
              ))}
          </ul>
        )}
      </div>
    </section>
  );
}
