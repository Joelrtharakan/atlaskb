"use client";

import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { ContourProgress } from "@/components/ui/ContourProgress";
import { EmptyState } from "@/components/ui/EmptyState";
import { ApiError, api } from "@/lib/api";
import { formatScore } from "@/lib/format";
import type { SearchResponse } from "@/lib/types";

// Raw hybrid retrieval, exposed for demoing quality independent of generation.
// Scores are system facts → mono, tabular. No generation, no citations here.
export function SearchView() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

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
    <section className="mx-auto flex h-full max-w-4xl flex-col gap-6 p-4 sm:p-8">
      <div>
        <h1 className="font-display text-3xl font-medium text-ink">Search</h1>
        <p className="mt-1 text-sm text-graphite">
          Inspect hybrid retrieval directly — dense vectors and full-text, fused and ranked. This is
          what the chat answer draws from.
        </p>
      </div>

      <form onSubmit={onSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <label
            htmlFor="search-input"
            className="font-mono text-xs uppercase tracking-cartouche text-graphite"
          >
            Query
          </label>
          <input
            id="search-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. how does billing work?"
            className="mt-1.5 w-full rounded-none border border-graphite/50 bg-linen/60 px-3 py-2 text-ink placeholder:text-graphite/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter focus-visible:ring-offset-2 focus-visible:ring-offset-linen"
          />
        </div>
        <Button type="submit" disabled={pending || query.trim().length === 0}>
          {pending ? (
            <>
              <ContourProgress size={16} label="Searching" />
              Searching…
            </>
          ) : (
            "Search"
          )}
        </Button>
      </form>

      {error ? (
        <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
          {error}
        </p>
      ) : null}

      <div className="min-h-0 flex-1">
        {results === null ? (
          <EmptyState title="Nothing searched yet —">
            enter a query above to see which chunks answer it, ranked by relevance.
          </EmptyState>
        ) : results.results.length === 0 ? (
          <EmptyState title="No chunks matched —">
            try different words, or upload a document that covers this topic.
          </EmptyState>
        ) : (
          <ol className="flex flex-col gap-3">
            {results.results.map((chunk, i) => (
              <li key={chunk.chunk_id} className="border border-graphite/30 p-4">
                <div className="marginalia flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.7rem]">
                  <span className="text-ink">#{i + 1}</span>
                  <span>fused {formatScore(chunk.score)}</span>
                  <span>dense {formatScore(chunk.dense_score)}</span>
                  <span>sparse {formatScore(chunk.sparse_score)}</span>
                  {chunk.page_num != null ? <span>page {chunk.page_num}</span> : null}
                </div>
                <p className="mt-2 text-sm leading-relaxed text-ink">{chunk.text}</p>
                <p className="marginalia mt-2 truncate text-[0.65rem] text-graphite">
                  {chunk.chunk_id}
                  {chunk.section ? ` · ${chunk.section}` : ""}
                </p>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
