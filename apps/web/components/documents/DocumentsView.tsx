"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { StatusBadge } from "@/components/ui/StatusBadge";
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

  return (
    <section className="mx-auto flex h-full max-w-4xl flex-col gap-6 p-4 sm:p-8">
      <div>
        <h1 className="font-display text-3xl font-medium text-ink">Documents</h1>
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

      <div className="min-h-0 flex-1 border border-graphite/30">
        {docs === null ? (
          <EmptyState title="Loading the register…" />
        ) : docs.length === 0 ? (
          <EmptyState title="Nothing mapped yet —">
            {canUpload
              ? "upload a document above to begin your survey."
              : "an editor or admin needs to upload documents to this workspace."}
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-sm">
              <caption className="sr-only">Your uploaded documents</caption>
              <thead>
                <tr className="border-b border-graphite/30">
                  <th scope="col" className="px-4 py-2 font-mono text-xs uppercase tracking-cartouche text-graphite">
                    Name
                  </th>
                  <th scope="col" className="px-4 py-2 font-mono text-xs uppercase tracking-cartouche text-graphite">
                    Status
                  </th>
                  <th scope="col" className="px-4 py-2 font-mono text-xs uppercase tracking-cartouche text-graphite">
                    Uploaded
                  </th>
                </tr>
              </thead>
              <tbody>
                {docs.map((doc) => (
                  <tr key={doc.id} className="border-b border-graphite/15 last:border-0">
                    <td className="px-4 py-3">
                      <Link
                        href={`/documents/${doc.id}`}
                        className="text-ink underline decoration-pewter underline-offset-4 hover:decoration-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-pewter"
                      >
                        {doc.filename}
                      </Link>
                      {doc.status === "failed" && doc.error ? (
                        <p className="mt-1 text-xs text-graphite">
                          Survey failed: {doc.error}. Fix the file and upload it again.
                        </p>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={doc.status} />
                    </td>
                    <td className="marginalia px-4 py-3 text-xs">{formatDate(doc.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
