"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { DocumentOut, ReliefCell } from "@/lib/types";

// three.js only loads for this route, and only after the page shell is up.
const ReliefMap = dynamic(() => import("./ReliefMap").then((m) => m.ReliefMap), {
  ssr: false,
  loading: () => <div className="h-full w-full animate-pulse bg-ink/5" aria-hidden />,
});

export function DashboardView() {
  const router = useRouter();
  const [cells, setCells] = useState<ReliefCell[] | null>(null);
  const [docs, setDocs] = useState<DocumentOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ask, setAsk] = useState("");

  const load = useCallback(async () => {
    try {
      const [relief, list] = await Promise.all([api.relief(), api.listDocuments()]);
      setCells(relief.cells);
      setDocs(list);
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn't load the dashboard. Check the backend is running and refresh.",
      );
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const recent = (docs ?? []).slice(0, 6);
  const staleCount = (cells ?? []).filter((c) => c.staleness > 0.5).length;

  return (
    <section className="mx-auto flex min-h-full max-w-5xl flex-col gap-6 p-4 sm:p-8">
      <header>
        <p className="font-mono text-xs uppercase tracking-cartouche text-graphite">
          Northwind Survey
        </p>
        <h1 className="font-display text-3xl font-medium text-ink">Dashboard</h1>
        <p className="mt-1 text-sm text-graphite">
          Your knowledge landscape. Peaks are large, freshly-verified documents; valleys are
          documents going stale.
        </p>
      </header>

      {error && (
        <p className="border border-graphite/30 bg-linen/50 px-4 py-3 text-sm text-graphite">
          {error}
        </p>
      )}

      {/* The one alive element on the page: the relief map. */}
      <div className="shrink-0 overflow-hidden rounded-lg border border-graphite/25 bg-ink/[0.03]">
        <div className="h-[320px] w-full">
          {cells && cells.length > 0 ? (
            <ReliefMap cells={cells} />
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-graphite">
              {cells ? "No documents yet — upload one to raise your first hill." : "Surveying…"}
            </div>
          )}
        </div>
        <div className="flex items-center justify-between border-t border-graphite/20 px-4 py-2 font-mono text-xs text-graphite">
          <span>{cells?.length ?? 0} documents mapped</span>
          <span>
            {staleCount > 0
              ? `${staleCount} in the fog (going stale)`
              : "all recently verified"}
          </span>
        </div>
      </div>

      {/* Everything below stays flat and quiet. */}
      <div className="grid gap-6 sm:grid-cols-2">
        <div>
          <h2 className="font-display text-lg text-ink">Recent documents</h2>
          {recent.length === 0 ? (
            <EmptyState title="Nothing here yet">Uploaded documents will appear here.</EmptyState>
          ) : (
            <ul className="mt-2 divide-y divide-graphite/15">
              {recent.map((d) => (
                <li key={d.id} className="flex items-center justify-between py-2">
                  <Link
                    href={`/documents/${d.id}`}
                    className="truncate text-sm text-ink hover:text-pewter"
                  >
                    {d.filename}
                  </Link>
                  <span className="ml-3 flex shrink-0 items-center gap-2">
                    {typeof d.staleness === "number" && d.staleness > 0.5 && (
                      <span className="font-mono text-[10px] uppercase text-graphite">stale</span>
                    )}
                    <StatusBadge status={d.status} />
                    <span className="font-mono text-[10px] text-graphite">
                      {formatDate(d.created_at)}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <h2 className="font-display text-lg text-ink">Quick ask</h2>
          <form
            className="mt-2 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              router.push("/chat");
            }}
          >
            <input
              value={ask}
              onChange={(e) => setAsk(e.target.value)}
              placeholder="Ask the atlas a question…"
              className="w-full border border-graphite/30 bg-linen/40 px-3 py-2 text-sm text-ink outline-none focus:border-pewter"
            />
            <button
              type="submit"
              className="shrink-0 border border-graphite/40 px-3 py-2 text-sm text-ink hover:border-pewter"
            >
              Ask
            </button>
          </form>
          <p className="mt-2 text-xs text-graphite">Opens the chat with the Living Atlas.</p>
        </div>
      </div>
    </section>
  );
}
