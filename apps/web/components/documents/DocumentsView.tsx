"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { ContourRing } from "@/components/ui/ContourRing";
import { EmptyState } from "@/components/ui/EmptyState";
import { SplitText } from "@/components/ui/SplitText";
import { ApiError, api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { DocumentOut } from "@/lib/types";
import { useWorkspace } from "@/lib/workspace";

import { UploadControl } from "./UploadControl";

const POLL_MS = 2000;

export function DocumentsView() {
  const { role } = useWorkspace();
  const canUpload = role === "admin" || role === "editor";
  const [docs, setDocs] = useState<DocumentOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const refresh = useCallback(async () => {
    try {
      const list = await api.listDocuments();
      setDocs(list);
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn't load your documents. Check the backend is running and refresh.",
      );
    }
  }, []);

  useEffect(() => {
    refresh();
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [refresh]);

  // While any document is still being surveyed, poll the register until it settles.
  const processing = (docs ?? []).filter((d) => d.status === "processing").length;
  useEffect(() => {
    if (processing === 0) return;
    pollRef.current = setTimeout(refresh, POLL_MS);
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [processing, docs, refresh]);

  function handleUploaded(doc: DocumentOut) {
    setDocs((prev) => [doc, ...(prev ?? []).filter((d) => d.id !== doc.id)]);
  }

  // Unlike a fresh upload, a retry updates the existing row in place — moving
  // it to the top would read as a duplicate/new document, not a retry.
  function handleRetried(doc: DocumentOut) {
    setDocs((prev) => (prev ?? []).map((d) => (d.id === doc.id ? doc : d)));
  }

  return (
    <section className="mx-auto flex h-full max-w-4xl flex-col gap-6 p-4 sm:p-8">
      <div>
        <h1 className="font-display text-3xl font-medium text-ink">
          <SplitText text="Documents" />
        </h1>
        <p className="mt-1 text-sm text-graphite">
          Your surveyed territory. Upload sources and watch them chart to <em>ready</em>.
        </p>
      </div>

      {canUpload ? (
        <UploadControl onUploaded={handleUploaded} />
      ) : (
        <p className="border border-graphite/30 bg-linen/50 px-4 py-3 text-sm text-graphite">
          You have <span className="text-ink">viewer</span> access to this workspace — you can search
          and chat, but only editors and admins can upload documents.
        </p>
      )}

      {/* Live summary for assistive tech. */}
      <p aria-live="polite" className="sr-only">
        {processing > 0 ? `${processing} document${processing === 1 ? "" : "s"} surveying.` : ""}
      </p>

      {error ? (
        <p role="alert" className="border border-ink bg-ink/5 px-3 py-2 text-sm text-ink">
          {error}
        </p>
      ) : null}

      <div className="min-h-0 flex-1">
        {docs === null ? (
          <EmptyState title="Loading the register…" />
        ) : docs.length === 0 ? (
          <EmptyState title="Nothing mapped yet —">
            {canUpload
              ? "upload a document above to begin your survey."
              : "an editor or admin needs to upload documents to this workspace."}
          </EmptyState>
        ) : (
          <ul className="doc-rack flex flex-col gap-2.5">
            {docs.map((doc) => {
              const stuck =
                doc.status === "processing" && Date.now() - new Date(doc.created_at).getTime() > 60_000;
              return (
                <li key={doc.id} className="doc-plate group flex items-center gap-4 rounded-sm px-4 py-3.5">
                  <Link
                    href={`/documents/${doc.id}`}
                    className="flex min-w-0 flex-1 items-center gap-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass"
                  >
                    <ContourRing status={doc.status} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm text-parchment">{doc.filename}</span>
                      {/* Mono metadata slides in as the plate tilts forward. */}
                      <span className="plate-meta mt-0.5 flex flex-wrap gap-x-3 font-mono text-[10px] text-graphite">
                        <span>{doc.status}</span>
                        <span>· {formatDate(doc.created_at)}</span>
                        <span className="truncate">· {doc.id.slice(0, 8)}</span>
                      </span>
                      {doc.status === "failed" && doc.error ? (
                        <span className="mt-1 block text-xs text-signal-red">
                          Survey failed: {doc.error}
                        </span>
                      ) : null}
                      {stuck ? (
                        <span className="mt-1 block text-xs text-brass/80">
                          Taking longer than usual — the job may have been lost.
                        </span>
                      ) : null}
                    </span>
                    <span className="font-mono text-[10px] uppercase tracking-cartouche text-graphite">
                      open →
                    </span>
                  </Link>
                  {(doc.status === "failed" || stuck) && canUpload ? (
                    <RetryButton documentId={doc.id} onRetried={handleRetried} />
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

function RetryButton({
  documentId,
  onRetried,
}: {
  documentId: string;
  onRetried: (doc: DocumentOut) => void;
}) {
  const [pending, setPending] = useState(false);

  async function onClick(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (pending) return;
    setPending(true);
    try {
      const updated = await api.retryDocument(documentId);
      onRetried(updated);
    } catch {
      // The row's own status/error will still reflect reality on the next
      // poll — a toast here would be one more thing to dismiss for a low-
      // stakes action the user can just click again.
    } finally {
      setPending(false);
    }
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={pending}
      className="shrink-0 rounded-sm border border-brass/50 px-2.5 py-1 font-mono text-[10px] uppercase tracking-cartouche text-brass transition-colors hover:bg-brass/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brass disabled:opacity-50"
    >
      {pending ? "Retrying…" : "Retry"}
    </button>
  );
}
