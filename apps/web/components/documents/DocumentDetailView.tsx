"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ContourProgress } from "@/components/ui/ContourProgress";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError, api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ChunkSample, DocumentDetail } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace";

import { AccessScopeControl } from "./AccessScopeControl";
import { CoreSample } from "./CoreSample";
import { SurveyGrid } from "./SurveyGrid";
import { VersionHistory } from "./VersionHistory";

const POLL_MS = 2000;

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 border-b border-graphite/15 py-3 sm:flex-row sm:items-baseline sm:gap-4">
      <dt className="font-mono text-xs uppercase tracking-cartouche text-graphite sm:w-40 sm:shrink-0">
        {label}
      </dt>
      <dd className="text-sm text-ink">{children}</dd>
    </div>
  );
}

export function DocumentDetailView({ id }: { id: string }) {
  const { active } = useWorkspace();
  const [doc, setDoc] = useState<DocumentDetail | null>(null);
  const [layers, setLayers] = useState<ChunkSample[] | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const detail = await api.getDocument(id);
      setDoc(detail);
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn't load this document. Check the backend is running and refresh.",
      );
    }
  }, [id]);

  useEffect(() => {
    load();
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [load]);

  useEffect(() => {
    if (doc?.status !== "processing") return;
    pollRef.current = setTimeout(load, POLL_MS);
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [doc, load]);

  // Once the survey completes, pull the strata for the Core Sample.
  useEffect(() => {
    if (doc?.status !== "ready") return;
    let cancelled = false;
    api
      .documentChunks(id)
      .then((r) => !cancelled && setLayers(r.layers))
      .catch(() => !cancelled && setLayers([]));
    return () => {
      cancelled = true;
    };
  }, [doc?.status, id]);

  const hoveredChunk = useMemo(
    () => layers?.find((l) => l.chunk_id === hovered) ?? null,
    [layers, hovered],
  );

  async function handleRetry() {
    if (retrying) return;
    setRetrying(true);
    try {
      const updated = await api.retryDocument(id);
      setDoc(updated);
      setLayers(null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Couldn't retry this document. Try again.",
      );
    } finally {
      setRetrying(false);
    }
  }

  return (
    <section className="mx-auto flex min-h-full max-w-4xl flex-col gap-6 p-4 sm:p-8">
      <Link
        href="/documents"
        className="font-mono text-xs uppercase tracking-cartouche text-graphite hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
      >
        ← All documents
      </Link>

      {error ? (
        <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
          {error}
        </p>
      ) : doc === null ? (
        <div className="flex items-center gap-3 text-graphite">
          <ContourProgress size={24} label="Loading document" />
          <span className="text-sm">Loading…</span>
        </div>
      ) : (
        <>
          <div>
            <p className="marginalia text-[0.7rem] uppercase tracking-cartouche text-graphite">
              Territory
            </p>
            <h1 className="mt-1 break-words font-display text-3xl font-medium text-ink">
              {doc.filename}
            </h1>
          </div>

          <dl className="border-t border-graphite/15">
            <Fact label="Status">
              <StatusBadge status={doc.status} />
            </Fact>
            <Fact label="Chunks">
              <span className="marginalia text-sm">{doc.chunk_count}</span>
              {doc.status === "processing" ? (
                <span className="ml-2 text-xs text-graphite">counting as the survey completes…</span>
              ) : null}
            </Fact>
            <Fact label="Type">
              <span className="marginalia text-sm">{doc.content_type}</span>
            </Fact>
            <Fact label="Document ID">
              <span className="marginalia break-all text-sm">{doc.id}</span>
            </Fact>
            <Fact label="Uploaded">
              <span className="marginalia text-sm">{formatDateTime(doc.created_at)}</span>
            </Fact>
            <Fact label="Updated">
              <span className="marginalia text-sm">{formatDateTime(doc.updated_at)}</span>
            </Fact>
            {doc.status === "failed" && doc.error ? (
              <Fact label="Failure">
                <span className="text-sm text-ink">
                  {doc.error}. Fix the file and upload it again.
                </span>
              </Fact>
            ) : null}
          </dl>

          {doc.status === "processing" ? (
            <div className="rounded-lg border border-graphite/20 bg-linen/30 p-4">
              <SurveyGrid label="Surveying document" />
            </div>
          ) : null}

          {doc.status === "ready" && layers && layers.length > 0 ? (
            <div>
              <p className="marginalia text-[0.7rem] uppercase tracking-cartouche text-graphite">
                Core sample
              </p>
              <p className="mt-1 text-sm text-graphite">
                Each stratum is a chunk — height is its length, color its embedding centrality
                (solid verdigris = representative, pale brass = outlier). Hover or click a layer to
                read it; {layers.length} chunks in this core.
              </p>
              <div data-testid="core-sample" className="mt-3 grid gap-4 sm:grid-cols-[1fr_1.3fr]">
                <div className="h-[420px] overflow-hidden rounded-lg border border-graphite/25 bg-ink/[0.03] p-2">
                  <CoreSample layers={layers} hoveredId={hovered} onHover={setHovered} />
                </div>
                <div className="rounded-lg border border-graphite/20 bg-linen/30 p-4">
                  {hoveredChunk ? (
                    <>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="rounded-sm bg-beacon/90 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-linen">
                          CHUNK {hoveredChunk.chunk_index}
                        </span>
                        <span className="font-mono text-[10px] uppercase tracking-cartouche text-graphite">
                          {hoveredChunk.page_num != null
                            ? `page ${hoveredChunk.page_num}`
                            : (hoveredChunk.section ?? "location unknown")}
                          {` · ${Math.round(hoveredChunk.confidence * 100)}% central`}
                        </span>
                      </div>
                      <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-ink">
                        {hoveredChunk.preview}
                        {hoveredChunk.length > hoveredChunk.preview.length ? "…" : ""}
                      </p>
                      <p className="marginalia mt-3 break-all text-[10px] text-graphite/70">
                        {hoveredChunk.chunk_id}
                      </p>
                    </>
                  ) : (
                    <p className="text-sm text-graphite">
                      Hover or click a stratum to read that chunk’s text.
                    </p>
                  )}
                </div>
              </div>
            </div>
          ) : null}

          {doc.status === "ready" && layers && layers.length === 0 ? (
            <div className="rounded-lg border border-signal-red/50 bg-signal-red/5 p-4">
              <p className="text-sm text-ink">
                This document is marked ready but has no searchable content in its current
                version — a survey inconsistency, not an empty file (a truly empty upload would
                have failed instead). Retrying re-runs ingestion from the stored file.
              </p>
              {doc.can_manage_access ? (
                <button
                  type="button"
                  onClick={handleRetry}
                  disabled={retrying}
                  className="mt-3 rounded-sm border border-signal-red/60 px-3 py-1.5 font-mono text-xs uppercase tracking-cartouche text-signal-red transition-colors hover:bg-signal-red/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-signal-red disabled:opacity-50"
                >
                  {retrying ? "Retrying…" : "Retry survey"}
                </button>
              ) : null}
            </div>
          ) : null}

          <VersionHistory doc={doc} onReuploaded={setDoc} />

          {doc.can_manage_access && active ? (
            <AccessScopeControl documentId={doc.id} workspaceId={active.id} />
          ) : null}

          {doc.status === "ready" ? (
            <div className="flex flex-wrap gap-3">
              <Link
                href="/chat"
                className="border-b border-pewter pb-0.5 font-mono text-xs uppercase tracking-cartouche text-ink hover:text-pewter focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
              >
                Ask a question →
              </Link>
              <Link
                href="/search"
                className="border-b border-pewter pb-0.5 font-mono text-xs uppercase tracking-cartouche text-ink hover:text-pewter focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
              >
                Inspect retrieval →
              </Link>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
