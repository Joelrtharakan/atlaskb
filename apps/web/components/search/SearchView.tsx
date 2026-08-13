"use client";

import { useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { ContourProgress } from "@/components/ui/ContourProgress";
import { EmptyState } from "@/components/ui/EmptyState";
import { SplitText } from "@/components/ui/SplitText";
import { ApiError, api } from "@/lib/api";
import { formatScore } from "@/lib/format";
import type { SearchResponse } from "@/lib/types";

import { ThreadsBackground } from "./ThreadsBackground";

// Raw hybrid retrieval, plotted like soundings on a chart. Scores are system
// facts → mono. Threads plot behind the field and intensify while typing.
export function SearchView() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [typing, setTyping] = useState(false);
  const typingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function onType(v: string) {
    setQuery(v);
    // Pulse the plotting lines while the operator is entering a bearing.
    setTyping(true);
    if (typingTimer.current) clearTimeout(typingTimer.current);
    typingTimer.current = setTimeout(() => setTyping(false), 500);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    const q = query.trim();
    if (!q || pending) return;
    setPending(true);
    setError(null);
    try {
      setResults(await api.search(q, 10));
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Search didn't reach the API. Check the backend is running and try again.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <section className="relative flex h-full flex-col">
      <ThreadsBackground active={typing || pending} />

      <div className="relative z-10 mx-auto flex h-full w-full max-w-4xl flex-col gap-6 overflow-y-auto p-4 sm:p-8">
        <div>
          <h1 className="font-display text-3xl font-medium text-ink">
            <SplitText text="Search" />
          </h1>
          <p className="mt-1 text-sm text-graphite">
            Plot a bearing — dense vectors and full-text, fused and ranked. Each result is a
            sounding, with its relevance read off like a depth.
          </p>
        </div>

        {/* Full-bleed coordinate input. */}
        <form onSubmit={onSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <span
              aria-hidden
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 font-mono text-brass"
            >
              ⌖
            </span>
            <input
              id="search-input"
              aria-label="Search query"
              value={query}
              onChange={(e) => onType(e.target.value)}
              placeholder="Enter bearing…"
              className="w-full cursor-crosshair rounded-none border-b-2 border-brass/50 bg-transparent py-3 pl-10 pr-3 font-mono text-lg text-parchment placeholder:text-graphite/60 focus:border-brass focus-visible:outline-none"
            />
          </div>
          <Button type="submit" disabled={pending || query.trim().length === 0}>
            {pending ? (
              <>
                <ContourProgress size={16} label="Plotting" />
                Plotting…
              </>
            ) : (
              "Plot"
            )}
          </Button>
        </form>

        {error ? (
          <p role="alert" className="border border-signal-red/60 bg-signal-red/10 px-3 py-2 text-sm text-parchment">
            {error}
          </p>
        ) : null}

        <div className="doc-rack min-h-0 flex-1">
          {results === null ? (
            <EmptyState title="No soundings yet —">
              enter a bearing above to plot which chunks answer it, ranked by relevance.
            </EmptyState>
          ) : results.results.length === 0 ? (
            <EmptyState title="No soundings returned —">
              try a different bearing, or upload a document that covers this topic.
            </EmptyState>
          ) : (
            <ol className="flex flex-col gap-2.5">
              {results.results.map((chunk, i) => (
                <li key={chunk.chunk_id}>
                  <div className="doc-plate group flex items-start gap-4 rounded-sm px-4 py-3">
                    <span className="mt-0.5 shrink-0 font-mono text-xs text-graphite">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="line-clamp-2 text-sm text-parchment">{chunk.text}</p>
                      <p className="plate-meta mt-1 flex flex-wrap gap-x-3 font-mono text-[10px] text-graphite">
                        <span>dense {formatScore(chunk.dense_score)}</span>
                        <span>sparse {formatScore(chunk.sparse_score)}</span>
                        {chunk.page_num != null ? (
                          <span>page {chunk.page_num}</span>
                        ) : chunk.section ? (
                          <span>{chunk.section}</span>
                        ) : null}
                        <span className="truncate">{chunk.chunk_id.slice(0, 8)}</span>
                      </p>
                    </div>
                    {/* Relevance read off like a depth measurement. */}
                    <span className="shrink-0 self-center font-mono text-sm text-brass">
                      — {formatScore(chunk.score)} —
                    </span>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </section>
  );
}
