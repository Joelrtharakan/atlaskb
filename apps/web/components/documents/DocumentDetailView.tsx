"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ContourProgress } from "@/components/ui/ContourProgress";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError, api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { DocumentDetail } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace";

import { AccessScopeControl } from "./AccessScopeControl";

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
  const [error, setError] = useState<string | null>(null);
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

  return (
    <section className="mx-auto flex h-full max-w-3xl flex-col gap-6 p-4 sm:p-8">
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
